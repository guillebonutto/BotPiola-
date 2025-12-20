import asyncio
import aiohttp
from telegram_bot import TelegramNotifier
from unittest.mock import MagicMock, patch

async def test_retry_logic():
    notifier = TelegramNotifier(token="123456:ABC-DEF", chat_id="123456")
    
    # Mocking aiohttp.ClientSession.post to return 429 then 200
    mock_response_429 = MagicMock()
    mock_response_429.status = 429
    mock_response_429.text = asyncio.Future()
    mock_response_429.text.set_result('{"ok":false,"error_code":429,"description":"Too Many Requests","parameters":{"retry_after":1}}')
    mock_response_429.json = asyncio.Future()
    mock_response_429.json.set_result({"ok":False,"error_code":429,"parameters":{"retry_after":1}})
    
    mock_response_200 = MagicMock()
    mock_response_200.status = 200
    mock_response_200.text = asyncio.Future()
    mock_response_200.text.set_result('{"ok":true,"result":{"message_id":123}}')
    mock_response_200.json = asyncio.Future()
    mock_response_200.json.set_result({"ok":True,"result":{"message_id":123}})

    # We need to mock the context manager as well
    class MockContextManager:
        def __init__(self, responses):
            self.responses = responses
            self.index = 0
        async def __aenter__(self):
            res = self.responses[self.index]
            self.index += 1
            return res
        async def __aexit__(self, exc_type, exc, tb):
            pass

    responses = [mock_response_429, mock_response_200]
    mock_cm = MockContextManager(responses)

    with patch('aiohttp.ClientSession.post', return_value=mock_cm):
        print("Testing send_message retry logic...")
        result = await notifier.send_message("Test message")
        if result == 123:
            print("OK: Retry logic worked for send_message")
        else:
            print(f"FAIL: Retry logic failed for send_message, result: {result}")

if __name__ == "__main__":
    asyncio.run(test_retry_logic())
