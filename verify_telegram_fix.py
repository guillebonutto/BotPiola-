
import asyncio
from unittest.mock import MagicMock, AsyncMock
import sys
import os

# Add local directory to path so we can import telegram_bot
sys.path.append(os.getcwd())

from telegram_bot import TelegramNotifier

async def test_private_response():
    print("--- Starting Verification: Private Response Fix ---")
    
    # 1. Setup Mock Notifier
    # We pass a dummy token and chat_id. We also mock the methods that would make network calls.
    notifier = TelegramNotifier("123456:ABC-DEF", "-999", owner_id=12345)
    
    # Mock send_message and send_photo to return a success indicator (message_id 1)
    notifier.send_message = AsyncMock(return_value=1)
    notifier.send_photo = AsyncMock(return_value=1)
    
    # Mock internal stats generation to avoid file I/O errors or empty data
    notifier._get_stats = MagicMock(return_value={
        'balance': 100.0, 
        'total_trades': 10, 
        'total_winrate': 50.0, 
        'total_pnl': 5.0, 
        'today_trades': 0, 
        'today_winrate': 0.0, 
        'today_pnl': 0.0,
        'start_date': '01/01/2026'
    })
    notifier._generate_chart = MagicMock(return_value=None) # No chart needed for this test

    # 2. Simulate User Interaction
    # Scenario: User (ID 12345) sends "/info" command in a Group Chat (ID -999)
    TEST_USER_ID = 12345
    TEST_GROUP_ID = -999
    
    update = {
        'update_id': 101,
        'message': {
            'message_id': 500,
            'from': {'id': TEST_USER_ID, 'first_name': 'Tester', 'is_bot': False},
            'chat': {'id': TEST_GROUP_ID, 'type': 'supergroup', 'title': 'Trading Group'},
            'text': '/info',
            'date': 1709999999
        }
    }

    print(f"Simulating command '/info' from User {TEST_USER_ID} in Group {TEST_GROUP_ID}...")

    # 3. Execute processing
    await notifier._process_update(update)

    # 4. Verify Results
    # We expect _handle_info to be called, which calls send_message.
    # The CRITICAL check is: Was send_message called with target_chat_id = TEST_USER_ID?
    
    print("\n--- Verifying Calls ---")
    
    if notifier.send_message.call_count == 0 and notifier.send_photo.call_count == 0:
        print("❌ FAIL: No messages were sent.")
        return

    # Check all calls to see where they were sent
    all_calls = notifier.send_message.call_args_list
    
    passed = False
    for i, call in enumerate(all_calls):
        args, kwargs = call
        target = kwargs.get('target_chat_id')
        msg_preview = args[0][:50] if args else "No Text"
        
        print(f"Call #{i+1}: Target={target} | Msg='{msg_preview}...'")
        
        if target == TEST_USER_ID:
            passed = True
        elif target == TEST_GROUP_ID:
            print("❌ FAIL: Message sent to Group ID!")
            passed = False
            break
            
    if passed:
        print("\n✅ SUCCESS: Response was sent to the User's Private ID.")
    else:
        print("\n❌ FAILURE: Response was NOT sent to the User's Private ID correctly.")

if __name__ == "__main__":
    asyncio.run(test_private_response())
