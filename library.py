from fastapi import FastAPI, Query, UploadFile, File, Form
from pydantic import BaseModel, Field
from typing import List
import os, uuid
import psycopg
from dotenv import load_dotenv
# ------------------ Config ------------------
app = FastAPI()

load_dotenv()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ------------------ Connect to PostgreSQL ------------------
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_PORT = os.getenv("DB_PORT")

# Create database connection
con = psycopg.connect(
    host=DB_HOST,
    dbname=DB_NAME,
    user=DB_USER,
    password=DB_PASSWORD,
    port=DB_PORT
)

# ------------------ Initialize table if not exists ------------------
with con.cursor() as cur:
    cur.execute("""
        CREATE TABLE IF NOT EXISTS books (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            author TEXT NOT NULL,
            publisher TEXT,
            cover_image_path TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    con.commit()

# ------------------ Models ------------------
class Book(BaseModel):
    id: int
    title: str = Field(..., min_length=3, max_length=100)
    author: str = Field(..., min_length=3, max_length=100)
    publisher: str | None = Field(None, min_length=3, max_length=100)
    cover_image_path: str | None

class SearchResponse(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int
    results: List[Book]

# ------------------ Routes ------------------

@app.post("/books", response_model=Book, status_code=201)
def add_book(
    title: str = Form(...),
    author: str = Form(...),
    publisher: str | None = Form(None, min_length=3, max_length=100),
    cover_image: UploadFile = File(None)
):
    cover_image_path = None
    if cover_image and cover_image.filename:
        file_name = str(uuid.uuid4()) + "_" + cover_image.filename
        file_path = os.path.join(UPLOAD_DIR, file_name)
        content = cover_image.file.read()
        with open(file_path, "wb") as f:
            f.write(content)
        cover_image_path = file_path
    publisher_value = publisher.strip() if publisher else None
    with con.cursor() as cur:
        cur.execute("""
            INSERT INTO books (title, author, publisher, cover_image_path)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """, (title.strip(), author.strip(), publisher_value, cover_image_path))
        book_id = cur.fetchone()[0]
        con.commit()

    return Book(
        id=book_id,
        title=title.strip(),
        author=author.strip(),
        publisher=publisher_value,
        cover_image_path=cover_image_path
    )

@app.get("/books", response_model=SearchResponse)
def get_all_books(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50)
):
    offset = (page - 1) * page_size
    with con.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM books")
        total = cur.fetchone()[0]

        cur.execute("""
            SELECT id, title, author, publisher, cover_image_path
            FROM books
            ORDER BY id
            LIMIT %s OFFSET %s
        """, (page_size, offset))
        rows = cur.fetchall()

    books = [Book(id=r[0], title=r[1], author=r[2], publisher=r[3], cover_image_path=r[4]) for r in rows]
    total_pages = (total + page_size - 1) // page_size

    return SearchResponse(
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        results=books
    )

@app.get("/books/search", response_model=SearchResponse)
def search_books(
    query: str = Query(..., min_length=3, max_length=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50)
):
    offset = (page - 1) * page_size
    query_lower = f"%{query.strip().lower()}%"

    with con.cursor() as cur:
        # total matching books
        cur.execute("""
            SELECT COUNT(*) FROM books
            WHERE LOWER(title) LIKE %s OR LOWER(author) LIKE %s OR LOWER(publisher) LIKE %s
        """, (query_lower, query_lower, query_lower))
        total = cur.fetchone()[0]

        # paginated results
        cur.execute("""
            SELECT id, title, author, publisher, cover_image_path
            FROM books
            WHERE LOWER(title) LIKE %s OR LOWER(author) LIKE %s OR LOWER(publisher) LIKE %s
            ORDER BY id
            LIMIT %s OFFSET %s
        """, (query_lower, query_lower, query_lower, page_size, offset))
        rows = cur.fetchall()

    books = [Book(id=r[0], title=r[1], author=r[2], publisher=r[3], cover_image_path=r[4]) for r in rows]
    total_pages = (total + page_size - 1) // page_size

    return SearchResponse(
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        results=books
    )