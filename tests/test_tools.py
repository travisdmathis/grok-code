import pytest
from unittest.mock import patch, AsyncMock
from grok_code.tools.file_ops import ReadTool, WriteTool, EditTool
from grok_code.tools.glob_grep import GlobTool, GrepTool
from grok_code.tools.bash import BashTool


@pytest.mark.asyncio
async def test_read_file(tmp_path):
    tool = ReadTool()
    test_file = tmp_path / "test.txt"
    test_file.write_text("line1\nline2\nline3\n")
    result = await tool.execute(file_path=str(test_file))
    assert "  1	line1" in result
    assert "  3	line3" in result


@pytest.mark.asyncio
async def test_read_offset_limit(tmp_path):
    tool = ReadTool()
    test_file = tmp_path / "test.txt"
    test_file.write_text("line1\nline2\nline3\nline4\n")
    result = await tool.execute(file_path=str(test_file), offset=2, limit=2)
    lines = result.split("\n")
    assert len(lines) == 2
    assert "  2	line2" in result
    assert "line1" not in result


@pytest.mark.asyncio
async def test_write_new(tmp_path):
    tool = WriteTool()
    test_file = tmp_path / "new.txt"
    content = "hello\nworld"
    result = await tool.execute(file_path=str(test_file), content=content)
    assert "Successfully wrote 11 bytes" in result
    assert test_file.read_text() == content


@pytest.mark.asyncio
async def test_write_existing_without_read(tmp_path):
    tool = WriteTool()
    test_file = tmp_path / "exist.txt"
    test_file.write_text("old")
    result = await tool.execute(file_path=str(test_file), content="new")
    assert "has not been read first" in result
    assert test_file.read_text() == "old"


@pytest.mark.asyncio
async def test_write_after_read(tmp_path):
    read_tool = ReadTool()
    write_tool = WriteTool()
    test_file = tmp_path / "test.txt"
    test_file.touch()
    await read_tool.execute(file_path=str(test_file))  # mark read
    result = await write_tool.execute(file_path=str(test_file), content="new content")
    assert "Successfully wrote" in result
    assert test_file.read_text() == "new content"


@pytest.mark.asyncio
async def test_edit_file(tmp_path):
    read_tool = ReadTool()
    edit_tool = EditTool()
    test_file = tmp_path / "edit.txt"
    test_file.write_text("old text\nanother old\n")
    await read_tool.execute(file_path=str(test_file))
    result = await edit_tool.execute(file_path=str(test_file), old_string="old", new_string="NEW")
    assert "Successfully replaced" in result
    content = test_file.read_text()
    assert "NEW text" in content
    assert "another NEW" not in content  # first only


@pytest.mark.asyncio
async def test_edit_replace_all(tmp_path):
    read_tool = ReadTool()
    edit_tool = EditTool()
    test_file = tmp_path / "edit.txt"
    test_file.write_text("old\nold\nold")
    await read_tool.execute(file_path=str(test_file))
    result = await edit_tool.execute(
        file_path=str(test_file), old_string="old", new_string="NEW", replace_all=True
    )
    assert "replaced 3" in result
    content = test_file.read_text()
    assert content.count("NEW") == 3


@pytest.mark.asyncio
async def test_glob(tmp_path):
    tool = GlobTool()
    (tmp_path / "a.py").touch()
    (tmp_path / "b.txt").touch()
    (tmp_path / "sub/c.py").parent.mkdir(parents=True)
    (tmp_path / "sub/c.py").touch()
    result = await tool.execute(pattern="*.py")
    assert "a.py" in result
    assert "b.txt" not in result
    result2 = await tool.execute(pattern="**/*.py")
    assert "c.py" in result2


@pytest.mark.asyncio
async def test_grep(tmp_path):
    tool = GrepTool()
    (tmp_path / "test.py").write_text('def foo():\n    print("hello world")\nfoo()')
    result = await tool.execute(pattern=r"print", path=str(tmp_path / "test.py"))
    assert 'test.py:2:     print("hello world")' in result


@pytest.mark.asyncio
@patch("asyncio.create_subprocess_shell")
async def test_bash(mock_shell, tmp_path):
    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate.return_value = (b"stdout\n", b"")
    mock_shell.return_value = mock_proc

    tool = BashTool()
    result = await tool.execute(command="echo test")
    assert "stdout" in result
