// Dragonfly rejects commands with more than 2^16 arguments ("invalid
// multibulk length"), so variadic commands over unbounded collections must
// be chunked well below that limit.
export const REDIS_COMMAND_ARG_CHUNK_SIZE = 16000;
