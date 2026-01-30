import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from grok_code.client import GrokClient, Message


@pytest.fixture
def mock_api_key(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "test-key")


@pytest.mark.asyncio
async def test_client_init(mock_api_key):
    """Test client initialization"""
    client = GrokClient(model="test-model")
    assert client.model == "test-model"
    assert client.api_key == "test-key"


def test_client_no_key():
    """Test missing API key raises ValueError"""
    with pytest.raises(ValueError):
        GrokClient(api_key=None)


@pytest.mark.asyncio
async def test_chat():
    """Test non-streaming chat"""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": "Hello!"}}]
    }

    with patch("grok_code.client.httpx.AsyncClient") as MockClient:
        mock_client = MockClient.return_value
        mock_post = AsyncMock(return_value=mock_response)
        mock_client.post = mock_post

        client = GrokClient(api_key="test")
        messages = [Message(role="user", content="hi")]
        msg = await client.chat(messages)

        assert msg.role == "assistant"
        assert msg.content == "Hello!"
        mock_post.assert_called_once()


@pytest.mark.asyncio
async def test_chat_stream():
    """Test streaming chat"""
    chunks = [
        'data: {"choices":[{"delta":{"content":"Hel"}}]}',
        'data: {"choices":[{"delta":{"content":"lo"}}]}',
        "data: [DONE]",
    ]
    mock_lines = AsyncMock()
    mock_lines.__aiter__ = AsyncMock(side_effect=chunks)

    mock_stream = MagicMock()
    mock_stream.__aenter__.return_value.aiter_lines.return_value = mock_lines

    with patch("grok_code.client.httpx.AsyncClient") as MockClient:
        mock_client = MockClient.return_value
        mock_client.stream.return_value.__aenter__.return_value = mock_stream

        content_parts = []

        def on_content(content):
            content_parts.append(content)

        client = GrokClient(api_key="test")
        msg = await client.chat_stream([Message(role="user", content="hi")], on_content=on_content)

        assert msg.role == "assistant"
        assert msg.content == "Hello"
        assert content_parts == ["Hel", "lo"]


@pytest.mark.asyncio
async def test_context_manager():
    """Test async context manager"""
    with patch("grok_code.client.httpx.AsyncClient"):
        async with GrokClient(api_key="test") as client:
            assert client is not None
