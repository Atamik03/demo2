import sqlite3
from pathlib import Path

import sqlite_vec


PROJECT_ROOT = Path(__file__).resolve().parents[2]

RAG_DATA_DIR = PROJECT_ROOT / "rag_data"
RAG_DATABASE_PATH = RAG_DATA_DIR / "rag.db"


def connect_rag_database() -> sqlite3.Connection:
    """Создаёт подключение к RAG-базе."""

    RAG_DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    connection = sqlite3.connect(
        RAG_DATABASE_PATH
    )

    connection.row_factory = sqlite3.Row

    connection.execute(
        "PRAGMA foreign_keys = ON"
    )

    connection.enable_load_extension(True)
    sqlite_vec.load(connection)
    connection.enable_load_extension(False)

    return connection


def create_tables(
    connection: sqlite3.Connection,
) -> None:
    """Создаёт таблицы документов, чанков и векторов."""

    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS rag_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL UNIQUE,
            document_name TEXT NOT NULL,
            document_code TEXT,
            version TEXT,
            effective_date TEXT,
            file_hash TEXT,
            indexed_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS rag_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chunk_key TEXT NOT NULL UNIQUE,
            document_id INTEGER NOT NULL,
            section_number TEXT,
            section_title TEXT,
            clause_start TEXT,
            clause_end TEXT,
            text TEXT NOT NULL,

            FOREIGN KEY (document_id)
                REFERENCES rag_documents(id)
                ON DELETE CASCADE
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS
        rag_chunk_vectors USING vec0(
            embedding float[1024]
        );
        """
    )

    connection.commit()


def initialize_database() -> None:
    connection = connect_rag_database()

    try:
        create_tables(connection)

        sqlite_vec_version = connection.execute(
            "SELECT vec_version()"
        ).fetchone()[0]

        print(
            f"База создана: {RAG_DATABASE_PATH}"
        )

        print(
            f"Версия sqlite-vec: "
            f"{sqlite_vec_version}"
        )

        tables = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type IN ('table', 'view')
            ORDER BY name
            """
        ).fetchall()

        print("Созданные таблицы:")

        for table in tables:
            print(f"  {table['name']}")

    finally:
        connection.close()


if __name__ == "__main__":
    initialize_database()





    