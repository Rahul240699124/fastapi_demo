from http import HTTPStatus

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.responses import JSONResponse

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


def status_phrase(code) -> str:
    """Turn a status code (e.g. 404 or "404") into its standard name ("Not Found")."""
    try:
        return HTTPStatus(int(code)).phrase
    except (ValueError, TypeError):
        return "An Error Occurred"


# Makes it usable in templates as: {{ some_code | status_phrase }}
templates.env.filters["status_phrase"] = status_phrase

posts: list[dict] =[
    {
        "id": 1,
        "title": "Introduction to FastAPI",
        "content": "FastAPI is a modern, high-performance web framework for building APIs with Python.",
        "published": True,
        "rating": 5,
    },
    {
        "id": 2,
        "title": "FastAPI Path and Query Parameters",
        "content": "Learn how path parameters, query parameters, and Pydantic models work together.",
        "published": True,
        "rating": 4,
    },
    {
        "id": 3,
        "title": "Draft: Asynchronous Database Operations",
        "content": "Exploring async SQLAlchemy, session management, and migrations in FastAPI.",
        "published": False,
        "rating": None,
    },
]

# response_class=HTMLResponse is used for reaturing the end point of an api in html formate.
# include_in_schema=False is used for not to show html responces in docs and redoc pages for separation from json responces apis

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
@app.get("/posts", include_in_schema=False)
# def home():
# return f"<h1>{posts[0]['title']}</h1></br><p>{posts[0]['content']}</p>"
def home(request: Request):
    return templates.TemplateResponse(
        request, 
        "home.html", 
        {"posts": posts, "title": "🏠 Home"},
    )

@app.get("/posts/{post_id}", response_class=HTMLResponse, include_in_schema=False)
def get_post_page(request: Request, post_id: int):
    post = next((post for post in posts if post["id"] == post_id), None)
    if post is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Post with id {post_id} not found",
        )
    return templates.TemplateResponse(
        request,
        "post.html",
        {"post": post, "title": post["title"]},
    )

@app.get("/api/posts")
def get_posts():
    return posts

@app.get("/api/posts/{post_id}")
def get_post(post_id: int):
    post = next((post for post in posts if post["id"] == post_id), None)
    if post is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Post with id {post_id} not found",
        )
    return post

@app.exception_handler(StarletteHTTPException)
def common_exception_handler(request: Request, exception:StarletteHTTPException):
    massage = (
        exception.detail
        if exception.detail
        else "An error occurred please try again later."
    )
    # := and = are different, := is used for assignment and comparison in the same line. and = is used for assignment only.
    if url := request.url.path:
        if url.startswith("/api"):
            return JSONResponse(
                status_code=exception.status_code,
                content={"detail": massage},
            )
            # return templates.TemplateResponse(
            #     request,
            #     "error.html",
            #     {
            #         "error": massage,
            #         "title": exception.status_code,
            #     },
            # )
            
    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "error": massage,
            "title": exception.status_code,
        },
    status_code=exception.status_code
    );

@app.exception_handler(RequestValidationError)
def validation_exception_handler(request: Request, exception: RequestValidationError):
    urlPath = request.url.path
    if urlPath.startswith("/api"):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": exception.errors()},
        )
    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "title": status.HTTP_422_UNPROCESSABLE_CONTENT,
            "error": "Unprocessable Entity: unable to be followed due to semantic errors.",
        },
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT
    )


