"""Connect a terminal to BOB's BLE motor/speaker test sketch."""
import asyncio
from bleak import BleakClient, BleakScanner

COMMAND_UUID = "abcdefab-1234-5678-1234-abcdefabcdef"


async def main():
    print("Looking for BOB-MotorTest...")
    device = await BleakScanner.find_device_by_name("BOB-MotorTest", timeout=15)
    if device is None:
        print("Not found. Check ESP32 power, Bluetooth permissions, and firmware.")
        return
    async with BleakClient(device) as client:
        print("Connected! F/B/L/R = move for 1 second; 0..9 = speed")
        print("S = stop; T = speaker test; H = status on USB Serial Monitor")
        print("Enter one command and press Return. Q = quit.")
        try:
            while client.is_connected:
                command = (await asyncio.to_thread(input, "BOB> ")).strip().upper()
                if command == "Q":
                    break
                if len(command) != 1 or command not in "FBLRSTH0123456789":
                    print("Use F, B, L, R, S, T, H, 0..9, or Q.")
                    continue
                await client.write_gatt_char(COMMAND_UUID, command.encode(), response=True)
                print("Sent:", command)
        finally:
            if client.is_connected:
                await client.write_gatt_char(COMMAND_UUID, b"S", response=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, EOFError):
        print("\nDisconnected.")
    except Exception as error:
        print(f"Bluetooth error: {error}")
