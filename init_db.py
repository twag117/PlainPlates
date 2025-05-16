import sqlite3
from datetime import datetime
import os

# Ensure directory exists for the database
os.makedirs('data', exist_ok=True)

# Connect to SQLite database (will create it if it doesn't exist)
conn = sqlite3.connect('data/plainplates.db')
cursor = conn.cursor()

# Create the tables
cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    google_id TEXT UNIQUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    description TEXT
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS recipes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    description TEXT NOT NULL,
    ingredients TEXT NOT NULL,
    instructions TEXT NOT NULL,
    notes TEXT,
    prep_time INTEGER NOT NULL,
    cook_time INTEGER NOT NULL,
    servings INTEGER NOT NULL DEFAULT 4,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    user_id INTEGER,
    FOREIGN KEY (user_id) REFERENCES users (id)
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS recipe_categories (
    recipe_id INTEGER,
    category_id INTEGER,
    PRIMARY KEY (recipe_id, category_id),
    FOREIGN KEY (recipe_id) REFERENCES recipes (id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES categories (id) ON DELETE CASCADE
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS recipe_votes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipe_id INTEGER NOT NULL,
    identifier TEXT NOT NULL, -- IP address or session hash
    value INTEGER NOT NULL,   -- +1 (like), -1 (dislike), +5/-5 if logged in
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (recipe_id) REFERENCES recipes (id) ON DELETE CASCADE
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS user_favorites (
    user_id INTEGER,
    recipe_id INTEGER,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, recipe_id),
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    FOREIGN KEY (recipe_id) REFERENCES recipes (id) ON DELETE CASCADE
)
''')

# Create indexes for better performance
cursor.execute('CREATE INDEX IF NOT EXISTS idx_recipes_slug ON recipes (slug)')
cursor.execute('CREATE INDEX IF NOT EXISTS idx_categories_slug ON categories (slug)')
cursor.execute('CREATE INDEX IF NOT EXISTS idx_recipe_votes_recipe_id ON recipe_votes (recipe_id)')
cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_favorites_user_id ON user_favorites (user_id)')

conn.commit()

# Insert some initial categories
categories = [
    ('Breakfast', 'breakfast', 'Morning meals to start your day right'),
    ('Lunch', 'lunch', 'Midday meals that are satisfying and quick'),
    ('Dinner', 'dinner', 'Evening meals for the whole family'),
    ('Dessert', 'dessert', 'Sweet treats and after-dinner delights'),
    ('Vegetarian', 'vegetarian', 'Meatless dishes full of flavor'),
    ('Vegan', 'vegan', 'Plant-based recipes with no animal products'),
    ('Quick & Easy', 'quick-easy', 'Recipes ready in 30 minutes or less'),
    ('Soups & Stews', 'soups-stews', 'Comforting bowls for any season'),
    ('Salads', 'salads', 'Fresh and crisp combinations'),
    ('Pasta', 'pasta', 'From classic spaghetti to creative noodle dishes'),
    ('Baking', 'baking', 'Breads, pastries, and other baked goods'),
    ('Grilling', 'grilling', 'Perfect for cookouts and BBQs'),
    ('Gluten Free', 'gluten-free', 'No gluten ingredients included'),
    ('High Protein', 'high-protein', 'Packed with protein to keep you full')
]

# Check if categories already exist to avoid duplicates
cursor.execute('SELECT COUNT(*) FROM categories')
if cursor.fetchone()[0] == 0:
    cursor.executemany('INSERT INTO categories (name, slug, description) VALUES (?, ?, ?)', categories)
    conn.commit()

# Import sample recipes
def import_sample_recipes():
    # Check if we already have recipes
    cursor.execute('SELECT COUNT(*) FROM recipes')
    if cursor.fetchone()[0] > 0:
        return  # Skip if we already have recipes
    
    # Create a sample user for our recipes
    # Replace admin with your info
    cursor.execute('INSERT OR IGNORE INTO users (email, name) VALUES (?, ?)', ('twag117@gmail.com', 'Travis Wagner'))

    conn.commit()
    
    cursor.execute('SELECT id FROM users WHERE email = ?', ('twag117@gmail.com',))
    user_id = cursor.fetchone()[0]
    
    # Sample recipes - we'll add 3 detailed ones
    recipes = [
        {
            'title': 'Classic Chocolate Chip Cookies',
            'slug': 'classic-chocolate-chip-cookies',
            'description': 'Perfect chewy chocolate chip cookies with crisp edges and soft centers.',
            'ingredients': '''
- 1 cup (2 sticks) unsalted butter, softened
- 3/4 cup granulated sugar
- 3/4 cup packed brown sugar
- 2 large eggs
- 2 teaspoons vanilla extract
- 2 1/4 cups all-purpose flour
- 1 teaspoon baking soda
- 1/2 teaspoon salt
- 2 cups semi-sweet chocolate chips
- 1 cup chopped walnuts (optional)
''',
            'instructions': '''
1. Preheat oven to 375°F (190°C).
2. In a large bowl, cream together the butter, granulated sugar, and brown sugar until smooth.
3. Beat in the eggs one at a time, then stir in the vanilla.
4. Combine the flour, baking soda, and salt in a separate bowl. Gradually add to the wet ingredients and mix until just blended.
5. Fold in the chocolate chips and walnuts if using.
6. Drop by rounded tablespoons onto ungreased baking sheets.
7. Bake for 9 to 11 minutes or until golden brown.
8. Cool on baking sheets for 2 minutes before removing to wire racks to cool completely.
''',
            'notes': 'For softer cookies, reduce baking time by 1-2 minutes. For crispier cookies, add 1-2 minutes.',
            'prep_time': 15,
            'cook_time': 10,
            'servings': 24,
            'categories': ['Dessert', 'Baking']
        },
        {
            'title': 'Quick Chicken Stir Fry',
            'slug': 'quick-chicken-stir-fry',
            'description': 'A fast weeknight dinner with chicken, vegetables and a simple sauce.',
            'ingredients': '''
- 1 lb boneless, skinless chicken breasts, cut into 1-inch pieces
- 2 tablespoons vegetable oil, divided
- 2 cups mixed vegetables (bell peppers, broccoli, carrots, snap peas)
- 3 cloves garlic, minced
- 1 tablespoon fresh ginger, grated
- 1/4 cup soy sauce
- 1 tablespoon honey
- 1 tablespoon cornstarch
- 1/4 cup water
- 2 green onions, sliced
- Cooked rice, for serving
''',
            'instructions': '''
1. In a small bowl, whisk together soy sauce, honey, cornstarch, and water. Set aside.
2. Heat 1 tablespoon oil in a large skillet or wok over medium-high heat.
3. Add chicken and cook until no longer pink, about 5-6 minutes. Remove and set aside.
4. Add remaining oil to the pan. Add vegetables, garlic, and ginger. Stir-fry for 3-4 minutes until vegetables are crisp-tender.
5. Return chicken to the pan. Pour sauce over and cook, stirring, until sauce thickens, about 1-2 minutes.
6. Garnish with sliced green onions and serve over rice.
''',
            'notes': 'You can swap the chicken for tofu or shrimp. Use any vegetables you have on hand.',
            'prep_time': 10,
            'cook_time': 10,
            'servings': 4,
            'categories': ['Dinner', 'Quick & Easy']
        },
        {
            'title': 'Classic Spaghetti Carbonara',
            'slug': 'classic-spaghetti-carbonara',
            'description': 'A simple authentic carbonara with eggs, cheese, bacon and black pepper.',
            'ingredients': '''
- 1 lb (450g) spaghetti
- 8 oz (225g) pancetta or guanciale, diced
- 4 large egg yolks
- 2 large whole eggs
- 1 cup (100g) Pecorino Romano cheese, freshly grated
- 1 cup (100g) Parmigiano Reggiano cheese, freshly grated
- 1 tablespoon olive oil
- Freshly ground black pepper
- Salt for pasta water
''',
            'instructions': '''
1. Bring a large pot of salted water to a boil. Add pasta and cook until al dente according to package directions.
2. While pasta cooks, heat olive oil in a large skillet over medium heat. Add pancetta and cook until crispy, about 5-7 minutes.
3. In a medium bowl, whisk together egg yolks, whole eggs, and grated cheeses. Season with black pepper.
4. When pasta is done, reserve 1 cup of pasta water, then drain.
5. Working quickly, add hot pasta to the skillet with pancetta. Toss to coat in the rendered fat.
6. Remove from heat. Add the egg and cheese mixture, stirring constantly. Add a splash of reserved pasta water to create a creamy sauce.
7. Serve immediately with extra grated cheese and freshly ground black pepper.
''',
            'notes': 'The key to carbonara is timing. The residual heat from the pasta cooks the eggs, but if it\'s too hot, they\'ll scramble. Keep everything moving and add pasta water as needed for silky texture.',
            'prep_time': 10,
            'cook_time': 15,
            'servings': 4,
            'categories': ['Dinner', 'Pasta']
        }
    ]
    
    # Insert recipes and their categories
    for recipe in recipes:
        cursor.execute('''
        INSERT INTO recipes (title, slug, description, ingredients, instructions, notes, 
                          prep_time, cook_time, servings, user_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (recipe['title'], recipe['slug'], recipe['description'], recipe['ingredients'],
              recipe['instructions'], recipe['notes'], recipe['prep_time'],
              recipe['cook_time'], recipe['servings'], user_id))
        
        recipe_id = cursor.lastrowid
        
        # Link recipe to categories
        for category_name in recipe['categories']:
            cursor.execute('SELECT id FROM categories WHERE name = ?', (category_name,))
            category_id = cursor.fetchone()[0]
            
            cursor.execute('''
            INSERT INTO recipe_categories (recipe_id, category_id)
            VALUES (?, ?)
            ''', (recipe_id, category_id))
    
    conn.commit()

# Import sample recipes
import_sample_recipes()

print("Database initialized with sample data!")
conn.close()