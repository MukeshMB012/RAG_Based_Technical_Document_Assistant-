# FastAPI Handling Errors

Source: https://fastapi.tiangolo.com/tutorial/handling-errors/

## Overview

APIs need to report errors to clients in many situations, such as when a
client lacks privileges, cannot access a resource, or requests an item
that does not exist.

Client-side errors normally use HTTP status codes in the 400--499 range.

## HTTPException

FastAPI uses `HTTPException` to return HTTP errors to clients.

Example:

``` python
from fastapi import FastAPI, HTTPException

app = FastAPI()

items = {"foo": "The Foo Wrestlers"}

@app.get("/items/{item_id}")
async def read_item(item_id: str):
    if item_id not in items:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"item": items[item_id]}
```

`HTTPException` is a Python exception with API-specific information.

It should be raised, not returned:

``` python
raise HTTPException(status_code=404, detail="Item not found")
```

When an `HTTPException` is raised inside a utility function used by a
path operation, FastAPI terminates the request and sends the HTTP error
response.

## Resulting Responses

For an existing item, the API can return a successful response:

``` json
{
  "item": "The Foo Wrestlers"
}
```

For a missing item, the API can return status code `404`:

``` json
{
  "detail": "Item not found"
}
```

The `detail` value can be any value that can be converted to JSON,
including a dictionary or list.

## Custom Headers

Custom headers can be included in an `HTTPException`:

``` python
raise HTTPException(
    status_code=404,
    detail="Item not found",
    headers={"X-Error": "There goes a problem"},
)
```

Custom headers can be useful for situations such as security-related
responses.

## Custom Exception Handlers

FastAPI allows applications to register custom exception handlers.

Example:

``` python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

class UnicornException(Exception):
    def __init__(self, name: str):
        self.name = name

app = FastAPI()

@app.exception_handler(UnicornException)
async def unicorn_exception_handler(request: Request, exc: UnicornException):
    return JSONResponse(
        status_code=418,
        content={"message": f"Oops! {exc.name} did something."},
    )

@app.get("/unicorns/{name}")
async def read_unicorn(name: str):
    if name == "yolo":
        raise UnicornException(name=name)
    return {"unicorn_name": name}
```

When `/unicorns/yolo` raises `UnicornException`, the registered handler
produces the configured response.

FastAPI also exposes response utilities from Starlette for convenience.

## Default Exception Handlers

FastAPI has default exception handlers for `HTTPException` and invalid
request data. These handlers can be overridden.

## RequestValidationError

When a request contains invalid data, FastAPI internally raises
`RequestValidationError` and provides a default handler.

A custom handler can be registered:

``` python
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import PlainTextResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

app = FastAPI()

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc):
    return PlainTextResponse(str(exc.detail), status_code=exc.status_code)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    message = "Validation errors:"
    for error in exc.errors():
        message += f"\n Field: {error['loc']}, Error: {error['msg']}"
    return PlainTextResponse(message, status_code=400)
```

## RequestValidationError Body

`RequestValidationError` contains the request body that caused the
validation error. It can be used during development for logging and
debugging.

Example:

``` python
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

app = FastAPI()

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError
):
    return JSONResponse(
        status_code=422,
        content=jsonable_encoder({
            "detail": exc.errors(),
            "body": exc.body
        }),
    )

class Item(BaseModel):
    title: str
    size: int

@app.post("/items/")
async def create_item(item: Item):
    return item
```

For invalid input such as:

``` json
{
  "title": "towel",
  "size": "XL"
}
```

the response contains validation details indicating that `size` was
invalid and can include the received body.

## FastAPI HTTPException vs Starlette HTTPException

FastAPI has its own `HTTPException`, which inherits from Starlette's
`HTTPException`.

FastAPI's version accepts any JSON-able value for the `detail` field,
while Starlette's version accepts strings.

Applications normally raise FastAPI's `HTTPException`. When registering
a general HTTP exception handler, the documentation recommends
registering the handler for Starlette's `HTTPException`, so exceptions
raised by Starlette internals or extensions can also be caught.

Example import:

``` python
from starlette.exceptions import HTTPException as StarletteHTTPException
```

## Reusing FastAPI Exception Handlers

FastAPI's default exception handlers can be imported and reused when
implementing custom handlers:

``` python
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
```

This allows additional logging or customization while retaining
FastAPI's normal error-response behavior.
