import asyncio

async def test_logic():
    print("Testing Win Case:")
    # Simulate (trade_id, details) for a WIN
    trade_result_win = ('12345', {'result': 'win', 'profit': 0.92, 'amount': 1.0})
    
    is_win = False
    profit = 0.0
    
    if isinstance(trade_result_win, tuple) and len(trade_result_win) == 2:
        _, details = trade_result_win
        is_win = details.get('result') == 'win'
        profit = details.get('profit', 0.0)
    
    print(f"  Result: {is_win}, Profit: {profit}")
    assert is_win is True
    assert profit == 0.92

    print("\nTesting Loss Case:")
    # Simulate (trade_id, details) for a LOSS
    trade_result_loss = ('12345', {'result': 'loss', 'profit': 0.0, 'amount': 1.0})
    
    is_win = False
    profit = 0.0
    
    if isinstance(trade_result_loss, tuple) and len(trade_result_loss) == 2:
        _, details = trade_result_loss
        is_win = details.get('result') == 'win'
        profit = details.get('profit', 0.0)
    
    print(f"  Result: {is_win}, Profit: {profit}")
    assert is_win is False
    assert profit == 0.0
    
    print("\nSUCCESS: Logic handles tuple correctly.")

if __name__ == "__main__":
    asyncio.run(test_logic())
