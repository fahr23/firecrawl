import { Logger } from "winston";
import { AddFeatureError, UnsupportedFileError } from "../../error";
import { FireEngineCheckStatusSuccess } from "../fire-engine/checkStatus";
import path from "path";
import os from "os";
import { writeFile } from "fs/promises";
import { Meta } from "../..";
import { documentExtensionFromContentType } from "../../../../lib/document-formats";

async function feResToFilePrefetch(
  logger: Logger,
  feRes: FireEngineCheckStatusSuccess | undefined,
  fileExtension: string,
  fileType: string,
  contentType?: string,
): Promise<Meta["pdfPrefetch"] | Meta["documentPrefetch"]> {
  if (!feRes?.file) {
    logger.warn(`No file in ${fileType} prefetch`);
    return null;
  }

  const filePath = path.join(
    os.tmpdir(),
    `tempFile-${crypto.randomUUID()}.${fileExtension}`,
  );
  await writeFile(filePath, Buffer.from(feRes.file.content, "base64"));

  return {
    status: feRes.pageStatusCode,
    url: feRes.url,
    filePath,
    proxyUsed: feRes.usedMobileProxy ? "stealth" : "basic",
    contentType,
  };
}

async function feResToPdfPrefetch(
  logger: Logger,
  feRes: FireEngineCheckStatusSuccess | undefined,
): Promise<Meta["pdfPrefetch"]> {
  return feResToFilePrefetch(logger, feRes, "pdf", "pdf");
}

async function feResToDocumentPrefetch(
  logger: Logger,
  feRes: FireEngineCheckStatusSuccess | undefined,
  contentType: string | undefined,
): Promise<Meta["documentPrefetch"]> {
  // Determine file extension from content type
  const extension =
    documentExtensionFromContentType(contentType)?.slice(1) ?? "tmp";

  return feResToFilePrefetch(logger, feRes, extension, "document", contentType);
}

/**
 * File types the parser engines can open, recognized from magic bytes.
 * Servers mislabel freely — a PDF behind a generic download endpoint comes
 * back as application/octet-stream or image/jp2, an Office file as
 * application/x-download — and a browser can only hand off what it could not
 * render, so once the header has failed to name a parseable type the bytes
 * decide which engine gets the file.
 */
type HandoffFileKind = "pdf" | "zip" | "ole";

const HANDOFF_FILE_SIGNATURES: Array<{
  kind: HandoffFileKind;
  bytes: number[];
}> = [
  // "%PDF-"
  { kind: "pdf", bytes: [0x25, 0x50, 0x44, 0x46, 0x2d] },
  // "PK\x03\x04": the local file header every OOXML/ODF container (.docx,
  // .xlsx, .pptx, .odt, ...) starts with. All four bytes, so a text body that
  // merely begins with "PK" is not mistaken for an archive.
  { kind: "zip", bytes: [0x50, 0x4b, 0x03, 0x04] },
  // OLE2/CFB header shared by legacy Office files (.doc, .xls, .ppt).
  { kind: "ole", bytes: [0xd0, 0xcf, 0x11, 0xe0, 0xa1, 0xb1, 0x1a, 0xe1] },
];

const HANDOFF_SNIFF_BYTES = Math.max(
  ...HANDOFF_FILE_SIGNATURES.map(s => s.bytes.length),
);

// Headers that already declare a ZIP archive. A ZIP signature under one of
// these confirms a real archive rather than exposing a mislabeled Office
// file, so it keeps the unsupported-file rejection instead of being sent to
// the document parser.
const ZIP_ARCHIVE_MEDIA_TYPES = new Set([
  "application/zip",
  "application/x-zip-compressed",
  "application/java-archive",
]);

function matchHandoffSignature(
  head: ArrayLike<number>,
): HandoffFileKind | null {
  for (const { kind, bytes } of HANDOFF_FILE_SIGNATURES) {
    if (head.length < bytes.length) continue;
    let matches = true;
    for (let i = 0; i < bytes.length; i++) {
      if (head[i] !== bytes[i]) {
        matches = false;
        break;
      }
    }
    if (matches) return kind;
  }
  return null;
}

/**
 * Identifies a handoff's file type from its leading bytes. A captured
 * download arrives base64-encoded in `file.content` (4 characters encode 3
 * bytes, so a short prefix covers the longest signature without decoding the
 * file); a body fire-engine returned as text sits in `content` and is
 * compared character by character.
 */
function sniffHandoffFileKind(
  feRes: FireEngineCheckStatusSuccess | undefined,
): HandoffFileKind | null {
  if (!feRes) return null;
  if (feRes.file?.content !== undefined) {
    const chars = Math.ceil(HANDOFF_SNIFF_BYTES / 3) * 4;
    const kind = matchHandoffSignature(
      Buffer.from(feRes.file.content.slice(0, chars), "base64"),
    );
    if (kind !== null) return kind;
  }
  return matchHandoffSignature(
    Array.from(feRes.content.slice(0, HANDOFF_SNIFF_BYTES), c =>
      c.charCodeAt(0),
    ),
  );
}

/**
 * Hands a sniffed file to the engine that parses it. `contentType` is the
 * header as served (undefined without one); the document engine only uses it
 * as an extension hint before falling back to the URL path and the
 * converter's own detection.
 */
async function handoffSniffedFile(
  kind: HandoffFileKind,
  logger: Logger,
  feRes: FireEngineCheckStatusSuccess | undefined,
  contentType: string | undefined,
): Promise<never> {
  if (kind === "pdf") {
    throw new AddFeatureError(["pdf"], await feResToPdfPrefetch(logger, feRes));
  }
  // OLE2 signature is shared by .doc/.xls/.ppt files
  // Only override to application/msword if URL suggests it's a .doc file
  const url = feRes?.url?.toLowerCase() ?? "";
  const isDocUrl = url.endsWith(".doc") || url.includes(".doc?");
  const effectiveContentType =
    kind === "ole" && isDocUrl ? "application/msword" : contentType;
  throw new AddFeatureError(
    ["document"],
    undefined,
    await feResToDocumentPrefetch(logger, feRes, effectiveContentType),
  );
}

export async function specialtyScrapeCheck(
  logger: Logger,
  headers: Record<string, string> | undefined,
  feRes?: FireEngineCheckStatusSuccess,
) {
  const contentType = (Object.entries(headers ?? {}).find(
    x => x[0].toLowerCase() === "content-type",
  ) ?? [])[1];

  if (!contentType) {
    // A header-less binary is still recognizable by its magic bytes.
    const headerlessFile = sniffHandoffFileKind(feRes);
    if (headerlessFile !== null) {
      await handoffSniffedFile(headerlessFile, logger, feRes, undefined);
    }
    logger.warn("Failed to check contentType -- was not present in headers", {
      headers,
    });
    return;
  }

  const isDocument = documentExtensionFromContentType(contentType) !== null;
  const isPdf =
    contentType === "application/pdf" ||
    contentType.startsWith("application/pdf;");

  // Check for document types first (before PDF to prioritize documents)
  if (isDocument) {
    throw new AddFeatureError(
      ["document"],
      undefined,
      await feResToDocumentPrefetch(logger, feRes, contentType),
    );
  }

  // Check for PDF (references were already handled above the header guard).
  if (isPdf) {
    throw new AddFeatureError(["pdf"], await feResToPdfPrefetch(logger, feRes));
  }

  const mediaType = contentType.split(";")[0].trim().toLowerCase();

  // The header named no parseable type, but the bytes may still: a PDF served
  // as application/octet-stream or image/jp2, an Office file behind a generic
  // download endpoint. The browser only hands off what it could not render,
  // so every remaining content type is sniffed, before the rejection below,
  // so a mislabeled PDF is parsed instead of failing as an unsupported file.
  const sniffedFile = sniffHandoffFileKind(feRes);
  if (
    sniffedFile !== null &&
    !(sniffedFile === "zip" && ZIP_ARCHIVE_MEDIA_TYPES.has(mediaType))
  ) {
    await handoffSniffedFile(sniffedFile, logger, feRes, contentType);
  }

  // Reject unsupported binary content types (images, video, audio, archives, etc.)
  const unsupportedBinaryPrefixes = [
    "image/",
    "video/",
    "audio/",
    "application/zip",
    "application/x-tar",
    "application/x-rar",
    "application/x-7z",
    "application/wasm",
    "application/x-executable",
    "application/x-sharedlib",
    "application/java-archive",
  ];
  if (
    unsupportedBinaryPrefixes.some(prefix => contentType.startsWith(prefix))
  ) {
    throw new UnsupportedFileError(contentType);
  }
}
