import json
import random

# ===== LOAD KB =====
with open("kb_demo_ai_seller_faq.json", "r", encoding="utf-8") as f:
    intents = json.load(f)

# ===== SIMPLE MATCHER (пример) =====
def match(query):
    query = query.lower()

    for intent, data in intents["intents"].items():
        for s in data["synonyms"]:
            if s in query:
                return intent

        for p in data["patterns"]:
            if p in query:
                return intent

    return "unknown"

# ===== NOISE =====
NOISE = ["бля", "pls", "??", "..."]
PREFIX = ["", "а", "слушай", "че", "ну"]
SUFFIX = ["", "сейчас", "быстро"]

def typo(word):
    if len(word) > 4:
        i = random.randint(0, len(word)-2)
        return word[:i] + word[i+1] + word[i] + word[i+2:]
    return word

def messify(text):
    words = text.split()

    if random.random() < 0.4:
        words = [typo(w) if random.random() < 0.3 else w for w in words]

    if random.random() < 0.5:
        words.append(random.choice(NOISE))

    if random.random() < 0.3:
        random.shuffle(words)

    return " ".join(words)

def mix_language(text):
    replacements = {
        "цена": "price",
        "стоимость": "cost",
        "сколько": "how much",
        "месяц": "month"
    }

    for ru, en in replacements.items():
        if ru in text and random.random() < 0.5:
            text = text.replace(ru, en)

    return text

# ===== GENERATOR =====
def generate_tests(n=10):
    tests = []

    for intent, data in intents["intents"].items():
        for _ in range(n):
            base = random.choice(data["synonyms"])

            q = mix_language(base)
            q = messify(q)

            q = random.choice(PREFIX) + " " + q + " " + random.choice(SUFFIX)

            tests.append((intent, q.strip()))

    return tests

# ===== RUN =====
tests = generate_tests(5)

ok = 0
fail = 0

for expected, query in tests:
    predicted = match(query)

    if predicted == expected:
        ok += 1
        print("✅", query, "→", predicted)
    else:
        fail += 1
        print("❌", query, "→", predicted, "| expected:", expected)

print("\nRESULT:")
print("OK:", ok)
print("FAIL:", fail)
