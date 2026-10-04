import subprocess
import random
import time

nodes = [
    "ledgersselens-postgres-shard-1-1", 
    "ledgersselens-postgres-shard-2-1", 
    "ledgersselens-postgres-shard-3-1", 
    "ledgersselens-api1-1", 
    "ledgersselens-api2-1", 
    "ledgersselens-api3-1"
]

print("🐒 Chaos Monkey Unleashed! Randomly assaulting nodes in 3 seconds...")
time.sleep(3)

while True:
    target = random.choice(nodes)
    print(f"\n🐒 Chaos Monkey targeted: {target}")
    
    # Kill it!
    print(f"🗡️  Assassinating {target}...")
    subprocess.run(["docker", "stop", target], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Wait for the system to suffer and trigger Circuit Breakers
    suffer_time = random.randint(15, 25)
    print(f"⏱️ Letting the system suffer for {suffer_time} seconds! (Try hitting the /api/insights endpoint right now!)")
    time.sleep(suffer_time)
    
    # Revive it
    print(f"✨ Reviving {target}...")
    subprocess.run(["docker", "start", target], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    print("💤 Monkey sleeping...")
    time.sleep(random.randint(10, 20))
