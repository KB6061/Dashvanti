from fastapi import HTTPException, Request


def https_or_internal(request: Request):
    if request.url.scheme != 'https' and (not request.client or request.client.host not in {'127.0.0.1', '::1'}):
        raise HTTPException(400, 'Payment APIs require HTTPS')
