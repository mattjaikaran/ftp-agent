from __future__ import annotations

from pathlib import Path

from ftp_agent.translation.legacy_parser import LegacyConfigParser


class TestParseCSV:
    def test_basic_csv(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "configs.csv"
        csv_file.write_text(
            "id,name,type,host,port,user,remote_dir\n"
            "f1,daily-feed,SFTP,sftp.example.com,22,admin,/data\n"
            "f2,weekly-report,FTP,ftp.example.com,21,user,/reports\n",
            encoding="utf-8",
        )
        parser = LegacyConfigParser()
        entries = parser.parse_csv(csv_file)

        assert len(entries) == 2
        assert entries[0].id == "f1"
        assert entries[0].name == "daily-feed"
        assert entries[0].protocol == "SFTP"
        assert entries[1].id == "f2"
        assert entries[1].name == "weekly-report"
        assert entries[1].protocol == "FTP"

    def test_missing_file_returns_empty(self) -> None:
        parser = LegacyConfigParser()
        entries = parser.parse_csv("/nonexistent/path/configs.csv")
        assert entries == []

    def test_csv_with_missing_columns_uses_defaults(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "minimal.csv"
        csv_file.write_text(
            "host,port\nsftp.example.com,22\n",
            encoding="utf-8",
        )
        parser = LegacyConfigParser()
        entries = parser.parse_csv(csv_file)

        assert len(entries) == 1
        entry = entries[0]
        # id should be a generated uuid prefix (8 chars)
        assert len(entry.id) == 8
        # name defaults to id when not provided
        assert entry.name == entry.id
        # protocol defaults to SFTP
        assert entry.protocol == "SFTP"

    def test_csv_legacy_config_contains_key_value_pairs(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "configs.csv"
        csv_file.write_text(
            "id,name,type\nf1,test-feed,SFTP\n",
            encoding="utf-8",
        )
        parser = LegacyConfigParser()
        entries = parser.parse_csv(csv_file)

        assert "id=f1" in entries[0].legacy_config
        assert "name=test-feed" in entries[0].legacy_config

    def test_csv_with_bom(self, tmp_path: Path) -> None:
        """UTF-8 BOM should be handled transparently."""
        csv_file = tmp_path / "bom.csv"
        csv_file.write_bytes(b"\xef\xbb\xbfid,name,type\nf1,bom-test,SFTP\n")
        parser = LegacyConfigParser()
        entries = parser.parse_csv(csv_file)

        assert len(entries) == 1
        assert entries[0].id == "f1"

    def test_csv_empty_rows_skipped(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "empty.csv"
        csv_file.write_text("id,name,type\n,,\n", encoding="utf-8")
        parser = LegacyConfigParser()
        entries = parser.parse_csv(csv_file)
        assert entries == []


class TestParseText:
    def test_basic_key_value(self) -> None:
        content = "id=f1\nname=my-feed\ntype=SFTP\nhost=sftp.example.com\nport=22\n"
        parser = LegacyConfigParser()
        entry = parser.parse_text(content, source_path="/configs/feed.cfg")

        assert entry.id == "f1"
        assert entry.name == "my-feed"
        assert entry.protocol == "SFTP"
        assert entry.legacy_config == content
        assert entry.source_path == "/configs/feed.cfg"

    def test_comments_and_blank_lines_ignored(self) -> None:
        content = "# This is a comment\n\nid=f2\n; another comment\nname=test\n"
        parser = LegacyConfigParser()
        entry = parser.parse_text(content)

        assert entry.id == "f2"
        assert entry.name == "test"

    def test_defaults_when_fields_missing(self) -> None:
        content = "host=sftp.example.com\nport=22\n"
        parser = LegacyConfigParser()
        entry = parser.parse_text(content)

        # id is a generated uuid prefix
        assert len(entry.id) == 8
        # name defaults to id when no source_path either
        assert entry.name == entry.id
        # protocol defaults to SFTP
        assert entry.protocol == "SFTP"

    def test_protocol_field_used(self) -> None:
        content = "protocol=FTP\nhost=ftp.example.com\n"
        parser = LegacyConfigParser()
        entry = parser.parse_text(content)
        assert entry.protocol == "FTP"

    def test_source_path_as_name_fallback(self) -> None:
        content = "host=sftp.example.com\n"
        parser = LegacyConfigParser()
        entry = parser.parse_text(content, source_path="/configs/my-feed.cfg")
        assert entry.name == "/configs/my-feed.cfg"


class TestParseINI:
    def test_multi_section_ini(self) -> None:
        content = (
            "[feed-alpha]\n"
            "type=SFTP\n"
            "host=sftp.alpha.com\n"
            "\n"
            "[feed-beta]\n"
            "type=FTP\n"
            "host=ftp.beta.com\n"
        )
        parser = LegacyConfigParser()
        entries = parser.parse_ini(content, source_path="/etc/feeds.ini")

        assert len(entries) == 2
        assert entries[0].name == "feed-alpha"
        assert entries[0].protocol == "SFTP"
        assert entries[1].name == "feed-beta"
        assert entries[1].protocol == "FTP"

    def test_no_sections_falls_back_to_text(self) -> None:
        content = "host=sftp.example.com\nport=22\n"
        parser = LegacyConfigParser()
        entries = parser.parse_ini(content)
        assert len(entries) == 1
        assert entries[0].protocol == "SFTP"


class TestParseDirectory:
    def test_parses_multiple_files(self, tmp_path: Path) -> None:
        (tmp_path / "alpha.cfg").write_text("id=a1\nname=alpha\ntype=SFTP\n")
        (tmp_path / "beta.txt").write_text("id=b1\nname=beta\ntype=FTP\n")
        # Non-config file should be ignored
        (tmp_path / "readme.md").write_text("# Not a config\n")

        parser = LegacyConfigParser()
        entries = parser.parse_directory(tmp_path)

        assert len(entries) == 2
        names = {e.name for e in entries}
        assert names == {"alpha", "beta"}

    def test_ini_files_use_ini_parser(self, tmp_path: Path) -> None:
        (tmp_path / "feeds.ini").write_text(
            "[section-a]\ntype=SFTP\nhost=a.com\n\n[section-b]\ntype=FTP\nhost=b.com\n"
        )
        parser = LegacyConfigParser()
        entries = parser.parse_directory(tmp_path)
        assert len(entries) == 2

    def test_empty_directory(self, tmp_path: Path) -> None:
        parser = LegacyConfigParser()
        entries = parser.parse_directory(tmp_path)
        assert entries == []
