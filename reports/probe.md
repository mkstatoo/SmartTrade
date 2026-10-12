# Provider probe

UTC: 2026-10-12 20:24:47

| chain | provider | usable | max getLogs range | p50 ms | p95 ms | burst errors /30 | depth 10k/100k/1M | agrees | first error |
|---|---|---|---|---|---|---|---|---|---|
| ethereum | publicnode | True | 1 | 197 | 250 | 0 | Y/Y/Y | True |  |
| ethereum | llamarpc | False | None | None | None | None | - | None | RpcError: HTTP 525: {"type":"https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-5xx- |
| ethereum | cloudflare | False | None | None | None | None | - | None | RpcError: Cannot fulfill request |
| ethereum | ankr | False | None | None | None | None | - | None | RpcError: malformed or mismatched JSON-RPC response: {"jsonrpc": "2.0", "error": {"code": -32000, "message": "Unauthorized: You mu |
| ethereum | drpc | True | 10 | 187 | 226 | 0 | Y/Y/Y | True |  |
| ethereum | 1rpc | False | None | None | None | None | - | None | RpcError: HTTP 502: {"type":"https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-5xx- |
| ethereum | private-1 | False | None | None | None | None | - | None | RpcError: HTTP 429: {"jsonrpc":"2.0","id":1,"error":{"code":-32003,"message":"daily request limit reached - upgrade your |
| ethereum | private-2 | True | 1 | 65 | 73 | 0 | Y/Y/Y | True |  |
| base | base-official | False | 0 | 87 | 95 | 0 | Y/Y/Y | None |  |
| base | publicnode | True | 1 | 192 | 219 | 0 | Y/Y/Y | None |  |
| base | llamarpc | False | None | None | None | None | - | None | RpcError: HTTP 525: {"type":"https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-5xx- |
| base | ankr | False | None | None | None | None | - | None | RpcError: malformed or mismatched JSON-RPC response: {"jsonrpc": "2.0", "error": {"code": -32000, "message": "Unauthorized: You mu |
| base | drpc | False | 0 | 202 | 246 | 14 | N/N/N | None | headers: RpcError: HTTP 429: {"id":43,"jsonrpc":"2.0","error":{"message":"You reached Public endpoint rate limit, please upgrade  |
| base | 1rpc | False | None | None | None | None | - | None | RpcError: HTTP 429: {"jsonrpc": "2.0", "id": null, "error": {"code": -32005, "message": "Rate limit exceeded on Nodies p |
| base | private-1 | False | None | None | None | None | - | None | RpcError: HTTP 402: Out of CU |

## Selection
```
{
 "ethereum": {
  "ranked": [
   "drpc",
   "private-2",
   "publicnode"
  ],
  "primary": "drpc",
  "verifier": "private-2",
  "ranges": {
   "drpc": 10,
   "private-2": 1,
   "publicnode": 1
  }
 },
 "base": {
  "ranked": [
   "publicnode"
  ],
  "primary": "publicnode",
  "verifier": null,
  "ranges": {
   "publicnode": 1
  }
 }
}
```
