"""Unit tests for the folder tools in tools/drive.py.

These are all API plumbing, so what is worth pinning down is the request the
code builds: the shared-drive flag, and that a move detaches the old parents
instead of adding a second one.
"""

from unittest.mock import MagicMock, patch

import pytest

from tools.drive import create_folder, list_shared_drives, move_file, move_to_folder

FOLDER_MIME = "application/vnd.google-apps.folder"


@pytest.fixture
def files():
    """Patch _drive() and hand back the mock files() resource."""
    with patch("tools.drive._drive") as drive:
        resource = MagicMock()
        drive.return_value.files.return_value = resource
        yield resource


class TestCreateFolder:
    def test_sets_folder_mime_type(self, files):
        files.create.return_value.execute.return_value = {
            "id": "f1", "name": "Matrimonios", "mimeType": FOLDER_MIME,
        }
        create_folder("Matrimonios")
        assert files.create.call_args.kwargs["body"]["mimeType"] == FOLDER_MIME

    def test_parent_becomes_parents_list(self, files):
        files.create.return_value.execute.return_value = {"id": "f1", "name": "x"}
        create_folder("Matrimonios", parent_id="drive123")
        assert files.create.call_args.kwargs["body"]["parents"] == ["drive123"]

    def test_no_parent_key_when_omitted(self, files):
        files.create.return_value.execute.return_value = {"id": "f1", "name": "x"}
        create_folder("Matrimonios")
        assert "parents" not in files.create.call_args.kwargs["body"]

    def test_supports_all_drives(self, files):
        files.create.return_value.execute.return_value = {"id": "f1", "name": "x"}
        create_folder("Matrimonios", parent_id="drive123")
        assert files.create.call_args.kwargs["supportsAllDrives"] is True

    def test_returns_formatted_file(self, files):
        files.create.return_value.execute.return_value = {
            "id": "f1", "name": "Matrimonios", "mimeType": FOLDER_MIME,
            "webViewLink": "https://drive.google.com/drive/folders/f1",
        }
        result = create_folder("Matrimonios")
        assert result["id"] == "f1"
        assert result["type"] == "folder"
        assert result["link"].endswith("/f1")


class TestMoveToFolder:
    def test_removes_every_old_parent(self, files):
        files.get.return_value.execute.return_value = {"parents": ["old1", "old2"]}
        files.update.return_value.execute.return_value = {"id": "d1", "parents": ["new"]}

        move_to_folder("d1", "new")

        kwargs = files.update.call_args.kwargs
        assert kwargs["addParents"] == "new"
        assert kwargs["removeParents"] == "old1,old2"

    def test_orphan_file_sends_no_remove_parents(self, files):
        files.get.return_value.execute.return_value = {}
        files.update.return_value.execute.return_value = {"id": "d1", "parents": ["new"]}

        move_to_folder("d1", "new")

        assert files.update.call_args.kwargs["removeParents"] is None

    def test_supports_all_drives_on_both_calls(self, files):
        files.get.return_value.execute.return_value = {"parents": ["old"]}
        files.update.return_value.execute.return_value = {"id": "d1", "parents": ["new"]}

        move_to_folder("d1", "new")

        assert files.get.call_args.kwargs["supportsAllDrives"] is True
        assert files.update.call_args.kwargs["supportsAllDrives"] is True


class TestMoveFile:
    def test_reports_new_parents(self, files):
        files.get.return_value.execute.return_value = {"parents": ["old"]}
        files.update.return_value.execute.return_value = {
            "id": "d1", "name": "Doc", "parents": ["new"],
            "webViewLink": "https://docs.google.com/document/d/d1/edit",
        }
        result = move_file("d1", "new")
        assert result["parents"] == ["new"]
        assert result["name"] == "Doc"


class TestListSharedDrives:
    def test_maps_drives_to_folder_links(self):
        with patch("tools.drive._drive") as drive:
            drive.return_value.drives.return_value.list.return_value.execute.return_value = {
                "drives": [{"id": "sd1", "name": "IdCR", "createdTime": "2025-01-01T00:00:00Z"}]
            }
            result = list_shared_drives()

        assert result == [{
            "id": "sd1",
            "name": "IdCR",
            "created": "2025-01-01T00:00:00Z",
            "link": "https://drive.google.com/drive/folders/sd1",
        }]

    def test_page_size_is_capped(self):
        with patch("tools.drive._drive") as drive:
            listing = drive.return_value.drives.return_value.list
            listing.return_value.execute.return_value = {"drives": []}
            list_shared_drives(max_results=5000)

        assert listing.call_args.kwargs["pageSize"] == 100
