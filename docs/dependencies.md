# FastAPI Dependencies

Source: https://fastapi.tiangolo.com/tutorial/dependencies/

## Overview

FastAPI provides a Dependency Injection system designed to make it easy
to integrate shared components and logic into path operation functions.

Dependency Injection allows a path operation function to declare what it
requires. FastAPI then takes care of providing those dependencies.

Dependencies are useful for:

-   Sharing common logic.
-   Sharing database connections.
-   Enforcing security, authentication, and role requirements.
-   Integrating external components while minimizing code repetition.

## Creating a Dependency

A dependency can be a function that accepts parameters in the same way
as a path operation function:

``` python
from typing import Annotated
from fastapi import Depends, FastAPI

app = FastAPI()

async def common_parameters(
    q: str | None = None,
    skip: int = 0,
    limit: int = 100
):
    return {"q": q, "skip": skip, "limit": limit}

@app.get("/items/")
async def read_items(
    commons: Annotated[dict, Depends(common_parameters)]
):
    return commons

@app.get("/users/")
async def read_users(
    commons: Annotated[dict, Depends(common_parameters)]
):
    return commons
```

The dependency can return any value. In this example it returns a
dictionary containing `q`, `skip`, and `limit`.

FastAPI recommends the `Annotated` form when possible.

## Using Depends

The dependency is passed to `Depends()` rather than called directly:

``` python
commons: Annotated[dict, Depends(common_parameters)]
```

You do not write `Depends(common_parameters())`. The function itself is
supplied to `Depends`.

When a request arrives, FastAPI:

1.  Calls the dependency function with the appropriate parameters.
2.  Gets the dependency result.
3.  Assigns that result to the parameter in the path operation function.

This lets shared code be written once and reused by multiple endpoints.

## Non-Annotated Form

The traditional form is also supported:

``` python
from fastapi import Depends, FastAPI

app = FastAPI()

async def common_parameters(
    q: str | None = None,
    skip: int = 0,
    limit: int = 100
):
    return {"q": q, "skip": skip, "limit": limit}

@app.get("/items/")
async def read_items(commons: dict = Depends(common_parameters)):
    return commons
```

## Annotated Dependencies

An `Annotated` dependency can be stored as a type alias and reused:

``` python
from typing import Annotated
from fastapi import Depends, FastAPI

app = FastAPI()

async def common_parameters(
    q: str | None = None,
    skip: int = 0,
    limit: int = 100
):
    return {"q": q, "skip": skip, "limit": limit}

CommonsDep = Annotated[dict, Depends(common_parameters)]

@app.get("/items/")
async def read_items(commons: CommonsDep):
    return commons

@app.get("/users/")
async def read_users(commons: CommonsDep):
    return commons
```

Because this is based on standard Python `Annotated`, type information
is preserved for editor support and tools such as `mypy`.

## Async or Normal Functions

Dependencies can be declared with either `async def` or normal `def`.
FastAPI handles both forms.

## OpenAPI Integration

Request declarations, validations, and requirements from dependencies
and sub-dependencies are integrated into the generated OpenAPI schema.
They therefore appear in the interactive API documentation.

## Dependency Injection Flow

A path operation function is called by FastAPI when its route and
operation match a request. Dependencies allow the path operation to
declare additional work that should be performed before it runs.

FastAPI executes the dependency and injects its result into the path
operation.

Common terms related to dependency injection include:

-   resources
-   providers
-   services
-   injectables
-   components

## Compatibility

FastAPI's dependency system can be used with:

-   Relational databases.
-   NoSQL databases.
-   External packages.
-   External APIs.
-   Authentication and authorization systems.
-   API usage monitoring.
-   Response data injection.

## Hierarchical Dependencies

Dependencies can themselves have dependencies. FastAPI builds a
dependency tree and resolves the dependencies and sub-dependencies
before providing the required values.

This makes it possible to express layered requirements such as current
user -\> active user -\> administrator or paying user.

All dependency requirements and validations are incorporated into the
OpenAPI schema.
