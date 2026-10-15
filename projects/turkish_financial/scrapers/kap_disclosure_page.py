"""
Identity of one KAP disclosure, read from its detail page (/tr/Bildirim/{index}).

KAP retired the JSON list APIs (memberDisclosureQuery, member/filter: live
failures 2026-10-15), but every detail page still embeds a `disclosureBasic`
object in its server-rendered payload. Verified on /tr/Bildirim/1680281:

  "disclosureBasic":{"title":"Genel Kurul İşlemlerine İlişkin Bildirim",
   "mkkMemberOid":"4028e4…","companyTitle":"BİRKO …","stockCode":"BRKO",
   "relatedStocks":null,"disclosureClass":"ODA","disclosureType":"CA",
   "disclosureCategory":"STT","publishDate":"2026.10.13 14:48:14",
   "disclosureId":"4028…","disclosureIndex":1680281,…,"isLate":false,…}
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

_MARKER = '"disclosureBasic":'
_ISTANBUL_UTC_OFFSET_HOURS = 3  # Türkiye has stayed on UTC+3 year-round since 2016


def extract_disclosure_basic(raw_html: str) -> Optional[Dict[str, Any]]:
    """The disclosure's canonical identity, or None when the page has none.

    Returns ``disclosure_index`` (str), ``stock_code``, ``related_stocks``,
    ``company_name``, ``title``, ``disclosure_class``, ``disclosure_type``,
    ``disclosure_category``, ``published_at`` (aware UTC), ``is_late``,
    ``attachment_count`` and ``mkk_member_oid``; absent values are None.
    """
    text = (raw_html or "").replace('\\"', '"')
    start = text.find(_MARKER)
    if start < 0:
        return None
    try:
        basic, _ = json.JSONDecoder().raw_decode(text, start + len(_MARKER))
    except ValueError:
        return None
    if not isinstance(basic, dict) or basic.get("disclosureIndex") in (None, ""):
        return None

    published_at = None
    raw_date = basic.get("publishDate")
    if raw_date:
        try:
            local = datetime.strptime(str(raw_date), "%Y.%m.%d %H:%M:%S")
            published_at = (local - timedelta(hours=_ISTANBUL_UTC_OFFSET_HOURS)).replace(tzinfo=timezone.utc)
        except ValueError:
            published_at = None

    stock_code = (basic.get("stockCode") or "").strip().upper() or None
    return {
        "disclosure_index": str(basic["disclosureIndex"]),
        "stock_code": stock_code.split(",")[0].strip() if stock_code else None,
        "related_stocks": basic.get("relatedStocks"),
        "company_name": basic.get("companyTitle"),
        "title": basic.get("title"),
        "disclosure_class": basic.get("disclosureClass"),
        "disclosure_type": basic.get("disclosureType"),
        "disclosure_category": basic.get("disclosureCategory"),
        "published_at": published_at,
        "is_late": basic.get("isLate"),
        "attachment_count": basic.get("attachmentCount"),
        "mkk_member_oid": basic.get("mkkMemberOid"),
    }
