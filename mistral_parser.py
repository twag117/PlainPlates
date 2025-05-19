import os
from dotenv import load_dotenv
from mistralai import Mistral

load_dotenv()

api_key = os.getenv("MISTRAL_API_KEY")
model = "mistral-small-latest"

client = Mistral(api_key=api_key)

recipe_text = """
BBQ BEEF RIBS
----------------------------------------------
Ingredients:
- 4.5 lbs beef ribs
- 2 tablespoons canola oil
- 5 tablespoons BBQ sauce (plus extra for additional saucing)
- 1 tablespoon salt
- 1 tablespoon pepper
- 1 tablespoon onion powder
- 1 tablespoon garlic powder

Instructions:
1. Preheat the oven to 385°F (196°C).
2. In a small bowl, mix together the salt, pepper, onion powder, and garlic powder.
3. Pat the ribs dry with paper towels.
4. Rub the canola oil over the ribs to lightly coat them.
5. Generously season the ribs with the mixed seasonings, ensuring all sides are covered.
6. Place the seasoned ribs in a baking pan and cover tightly with aluminum foil.
7. Cook in the preheated oven for 3.5 hours.
8. Remove the ribs from the oven and brush them with BBQ sauce.
9. Preheat the broiler.
10. Return the ribs to the oven, uncovered, and broil for 5 minutes to caramelize the BBQ sauce.
11. For extra saucy ribs, repeat the brushing with BBQ sauce and broiling step.
12. Remove from the oven and let the ribs rest for a few minutes before serving.
"""

chat_response = client.chat.complete(
    model="mistral-large-latest",
    messages=[
        {
            "role": "system",
            "content": (
                "You are a recipe parser. Convert the user's recipe into JSON with the following keys:\n"
                "title (string), description (string), ingredients (string), instructions (string), "
                "notes (optional string), prep_time (int in minutes), cook_time (int in minutes), servings (int).\n"
                "All units should stay as-is. Keep ingredients/instructions in original list format."
            ),
        },
        {"role": "user", "content": recipe_text},
    ],
)
print(chat_response.choices[0].message.content)

# model = "mistral-embed"

# client = Mistral(api_key=api_key)

# embeddings_response = client.embeddings.create(
#     model=model,
#     inputs=["Embed this sentence.", "As well as this one."]
# )

# print(embeddings_response)