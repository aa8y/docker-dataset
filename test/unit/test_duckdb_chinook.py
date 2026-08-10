"""Unit tests for duckdb/scripts/chinook/transform (Chinook_Sqlite.sql -> DuckDB).

A much smaller hook than the pgsql translators: two rewrites, each with one
sharp edge. debracket's failure mode is corrupting data -- Chinook track and
album titles genuinely contain ``[Disc 1]``-style brackets inside string
literals, so the quote-state walk is what the tests lean on. drop_foreign_keys'
failure mode is swallowing a neighbouring constraint along with the FOREIGN KEY
clause (the comma and optional referential actions are consumed with it).
"""


# --- debracket: [Ident] -> "Ident", quote-state aware ---------------------

def test_debracket_identifier(duckdb_chinook):
    assert duckdb_chinook.debracket("CREATE TABLE [Album]") == 'CREATE TABLE "Album"'


def test_debracket_keeps_brackets_inside_string_literal(duckdb_chinook):
    # Real Chinook data: album titles carry brackets that must survive.
    sql = "VALUES (1, 'BBC Sessions [Disc 1] [Live]')"
    assert duckdb_chinook.debracket(sql) == sql


def test_debracket_escaped_quote_does_not_end_literal(duckdb_chinook):
    # '' inside a literal is an escaped quote, not a close-then-open: the
    # bracket after it is still data.
    sql = "VALUES ('it''s [not] an identifier'), ([Col])"
    assert duckdb_chinook.debracket(sql) == 'VALUES (\'it\'\'s [not] an identifier\'), ("Col")'


def test_debracket_identifier_after_literal_closes(duckdb_chinook):
    assert duckdb_chinook.debracket("'x' AS [n]") == "'x' AS \"n\""


# --- drop_foreign_keys: FK clause + its comma + actions, nothing else -----

def test_drop_foreign_keys_removes_clause_and_actions(duckdb_chinook):
    sql = (
        'CREATE TABLE "Album"\n(\n'
        '    "AlbumId" INTEGER  NOT NULL,\n'
        '    CONSTRAINT "PK_Album" PRIMARY KEY  ("AlbumId"),\n'
        '    FOREIGN KEY ("ArtistId") REFERENCES "Artist" ("ArtistId") \n'
        '\t\tON DELETE NO ACTION ON UPDATE NO ACTION\n'
        ');'
    )
    out = duckdb_chinook.drop_foreign_keys(sql)
    assert "FOREIGN KEY" not in out
    assert "ON DELETE" not in out
    # The PRIMARY KEY constraint before it is untouched and the statement still
    # closes without a dangling comma.
    assert 'CONSTRAINT "PK_Album" PRIMARY KEY  ("AlbumId")\n);' in out


def test_drop_foreign_keys_removes_every_clause(duckdb_chinook):
    # Track carries three FKs back to back; all must go in one pass.
    sql = (
        '    CONSTRAINT "PK_Track" PRIMARY KEY  ("TrackId"),\n'
        '    FOREIGN KEY ("AlbumId") REFERENCES "Album" ("AlbumId") \n'
        '\t\tON DELETE NO ACTION ON UPDATE NO ACTION,\n'
        '    FOREIGN KEY ("GenreId") REFERENCES "Genre" ("GenreId") \n'
        '\t\tON DELETE NO ACTION ON UPDATE NO ACTION,\n'
        '    FOREIGN KEY ("MediaTypeId") REFERENCES "MediaType" ("MediaTypeId") \n'
        '\t\tON DELETE NO ACTION ON UPDATE NO ACTION\n'
    )
    out = duckdb_chinook.drop_foreign_keys(sql)
    assert "FOREIGN KEY" not in out
    assert '"PK_Track"' in out


# --- transform + main: end to end, in place -------------------------------

def test_transform_end_to_end(duckdb_chinook):
    sql = (
        "CREATE TABLE [Album]\n(\n"
        "    [Title] NVARCHAR(160)  NOT NULL,\n"
        "    CONSTRAINT [PK_Album] PRIMARY KEY  ([AlbumId]),\n"
        "    FOREIGN KEY ([ArtistId]) REFERENCES [Artist] ([ArtistId]) \n"
        "\t\tON DELETE NO ACTION ON UPDATE NO ACTION\n"
        ");\n"
        "INSERT INTO [Album] ([Title]) VALUES ('Live! [Disc 2]');\n"
    )
    out = duckdb_chinook.transform(sql)
    assert '"Album"' in out and "[Album]" not in out
    assert "FOREIGN KEY" not in out
    assert "'Live! [Disc 2]'" in out


def test_main_rewrites_sql_files_in_place(duckdb_chinook, tmp_path, monkeypatch):
    f = tmp_path / "Chinook_Sqlite.sql"
    f.write_text("DROP TABLE IF EXISTS [Album];\n", encoding="utf-8")
    monkeypatch.setenv("SQL_FILES", str(f))
    duckdb_chinook.main()
    assert f.read_text(encoding="utf-8") == 'DROP TABLE IF EXISTS "Album";\n'
