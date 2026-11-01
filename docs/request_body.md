# FastAPI Request Body

Source: https://fastapi.tiangolo.com/tutorial/body/

## Overview

When a client needs to send data to an API, it can send that data in the
request body. FastAPI uses Pydantic models to declare request bodies.

For sending data, the commonly used HTTP methods are `POST`, `PUT`,
`DELETE`, and `PATCH`. Sending a body with `GET` is discouraged because
its behavior is undefined in the specifications and intermediary proxies
may not support it.

## Declare a Request Body with Pydantic

Import `BaseModel` from Pydantic and define a model:

``` python
from fastapi import FastAPI
from pydantic import BaseModel

class Item(BaseModel):
    name: str
    description: str | None = None
    price: float
    tax: float | None = None

app = FastAPI()

@app.post("/items/")
async def create_item(item: Item):
    return item
```

The model inherits from `BaseModel` and uses standard Python type
annotations.

A field with a default value is not required. Using `None` makes an
optional field possible.

Example JSON:

``` json
{
  "name": "Foo",
  "description": "An optional description",
  "price": 45.2,
  "tax": 3.5
}
```

Because `description` and `tax` have defaults of `None`, this is also
valid:

``` json
{
  "name": "Foo",
  "price": 45.2
}
```

## What FastAPI Does

With the Pydantic model declaration, FastAPI:

-   Reads the request body as JSON.
-   Converts corresponding types when needed.
-   Validates the received data.
-   Reports validation errors with information about where the invalid
    data occurred.
-   Provides the validated data to the path operation function as the
    declared model type.
-   Generates JSON Schema definitions for the model.
-   Includes those schemas in the generated OpenAPI schema and automatic
    API documentation.

## Automatic Documentation

The JSON Schema generated for the Pydantic model is included in the
OpenAPI schema and displayed in FastAPI's interactive API documentation.

## Using the Model

Model attributes can be accessed directly. For example:

``` python
@app.post("/items/")
async def create_item(item: Item):
    item_dict = item.model_dump()
    if item.tax is not None:
        price_with_tax = item.price + item.tax
        item_dict.update({"price_with_tax": price_with_tax})
    return item_dict
```

## Request Body with Path Parameters

A path operation can receive both path parameters and a Pydantic request
body:

``` python
@app.put("/items/{item_id}")
async def update_item(item_id: int, item: Item):
    return {"item_id": item_id, **item.model_dump()}
```

FastAPI recognizes `item_id` as a path parameter and `item` as the
request body because `item` is a Pydantic model.

## Request Body with Path and Query Parameters

Body, path, and query parameters can all be declared together:

``` python
@app.put("/items/{item_id}")
async def update_item(item_id: int, item: Item, q: str | None = None):
    result = {"item_id": item_id, **item.model_dump()}
    if q:
        result.update({"q": q})
    return result
```

FastAPI determines the source of each parameter as follows:

-   A parameter declared in the path is a path parameter.
-   A singular type such as `int`, `float`, `str`, or `bool` is
    interpreted as a query parameter.
-   A parameter declared as a Pydantic model is interpreted as a request
    body.

A query parameter such as `q: str | None = None` is optional because it
has a default value of `None`.

## Without Pydantic

If Pydantic models are not desired, FastAPI also supports `Body`
parameters for request-body declarations.
