# character_sheet.py

import json
import os

class CharacterSheet:
    def __init__(self, file_path="assets/character.json"):
        self.file_path = file_path
        self.data = self.default_data()
        self.load()

    def default_data(self):
        return {
            "name": "Morgana",
            "class": "Witch (Necromancer)",
            "level": 1,
            "hit_points": 9,
            "armor_class": 12,
            "spell_slots": {"1st": 2},
            "ability_scores": {
                "STR": 8, "DEX": 14, "CON": 12,
                "INT": 16, "WIS": 12, "CHA": 17
            },
            "skills": ["Arcana", "History", "Insight", "Deception"],
            "proficiencies": ["Daggers", "Quarterstaffs", "Light Crossbows"],
            "spells_known": ["Mage Armour", "Ray of Sickness", "Cause Fear", "Disguise Self"],
            "cantrips": ["Chill Touch", "Prestidigitation", "Thaumaturgy"]
        }

    def load(self):
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r") as f:
                    loaded = json.load(f)
                    self.merge_defaults(loaded)
            except Exception as e:
                print(f"Error loading character sheet: {e}")

    def save(self):
        try:
            with open(self.file_path, "w") as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            print(f"Error saving character sheet: {e}")

    def merge_defaults(self, loaded):
        defaults = self.default_data()
        for key, val in defaults.items():
            if key not in loaded:
                loaded[key] = val
            elif isinstance(val, dict):
                for subkey in val:
                    if subkey not in loaded[key]:
                        loaded[key][subkey] = val[subkey]
        self.data = loaded

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value):
        self.data[key] = value

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.data[key] = value
