import asyncio
import glob
import json
import os
import random
import re
import sys
import threading
import uuid

import edge_tts
import speech_recognition as sr
from PyQt5 import QtGui
from PyQt5.QtCore import Qt, QMetaObject, Q_ARG
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QTextEdit,
                             QLineEdit, QPushButton, QLabel, QFileDialog, QHBoxLayout, QTextBrowser)
from dotenv import load_dotenv
from openai import OpenAI
from pydub import AudioSegment
from pydub.playback import play

from character_sheet import CharacterSheet
from foundry_bridge_ws import FoundryBridgeWSServer
from hybrid_engine import run_hybrid_engine


# Init once

def play_tts_audio(path):
    audio = AudioSegment.from_file(path, format="mp3")
    play(audio)

env_path = os.path.join(os.path.dirname(__file__), 'config', '.env')
load_dotenv(dotenv_path=env_path)
client = OpenAI(api_key=(os.getenv("OPENAI_KEY")))

recogniser = sr.Recognizer()
mic = sr.Microphone()
recogniser.energy_threshold = 400
recogniser.pause_threshold = 0.8
recogniser.dynamic_energy_threshold = True

SAVE_FILE = "save_data/dm_session.json"

ENV_STATE_FILE = "save_data/environment_state.json"

def inject_tag_instruction(history):
    tag_prompt = {
        "role": "system",
        "content": (
            "INSTRUCTIONS:\n"
            "- If your response includes character movement, you MUST include a tag like <<move:location_id>>.\n"
            "- For events, use <<event:event_id>>.\n"
            "- For cutscenes, use <<cutscene:id>>.\n"
            "- These tags are invisible to the player but required by the system.\n\n"
            "EXAMPLES:\n"
            "→ You enter the library. <<move:library>>\n"
            "→ A secret door opens. <<event:secret_door>>"
        )
    }
    # Optional: Remove old tag instructions if they exist
    history[:] = [msg for msg in history if "<<move:" not in msg.get("content", "")]
    history.append(tag_prompt)


class CharacterSheetEditor(QWidget):
    def __init__(self, character_sheet, parent=None):
        super().__init__(parent)
        self.character_sheet = character_sheet
        self.setWindowTitle("Edit Character Sheet")
        self.setGeometry(150, 150, 400, 600)
        self.setMinimumSize(400, 600)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(QtGui.QPalette.Window, Qt.white)
        self.setPalette(palette)

        self.layout = QVBoxLayout()
        self.layout.setSpacing(10)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.fields = {}
        self.load_character()

        save_button = QPushButton("Save Changes")
        save_button.clicked.connect(self.save_changes)
        self.layout.addWidget(save_button)

        self.setLayout(self.layout)

    def load_character(self):
        cs = self.character_sheet.data
        for key in ["name", "class", "level", "hit_points", "armor_class"]:
            label = QLabel(f"{key.capitalize()}:")
            line = QLineEdit(str(cs.get(key, "")))
            self.fields[key] = line
            self.layout.addWidget(label)
            self.layout.addWidget(line)

        self.layout.addWidget(QLabel("Ability Scores:"))
        self.ability_fields = {}
        for ability, score in cs["ability_scores"].items():
            line = QLineEdit(str(score))
            self.ability_fields[ability] = line
            self.layout.addWidget(QLabel(ability))
            self.layout.addWidget(line)

        self.spells_known_edit = QTextEdit("\n".join(cs["spells_known"]))
        self.cantrips_edit = QTextEdit("\n".join(cs["cantrips"]))
        self.layout.addWidget(QLabel("Spells Known:"))
        self.layout.addWidget(self.spells_known_edit)
        self.layout.addWidget(QLabel("Cantrips:"))
        self.layout.addWidget(self.cantrips_edit)

    def save_changes(self):
        cs = self.character_sheet.data
        for key, line in self.fields.items():
            val = line.text()
            cs[key] = int(val) if key in ["level", "hit_points", "armor_class"] else val
        cs["ability_scores"] = {k: int(v.text()) for k, v in self.ability_fields.items()}
        cs["spells_known"] = [s.strip() for s in self.spells_known_edit.toPlainText().splitlines() if s.strip()]
        cs["cantrips"] = [s.strip() for s in self.cantrips_edit.toPlainText().splitlines() if s.strip()]
        self.character_sheet.save()
        self.close()

class DMApp(QWidget):
    def __init__(self):
        super().__init__()
        self.conversation_history = []
        self.foundry = FoundryBridgeWSServer()
        threading.Thread(target=lambda: asyncio.run(self.foundry.start()), daemon=True).start()
        with open("assets/baldurs_gate_campaign.json", "r") as f:
            self.campaign = json.load(f)
        with open("assets/npc_voices.json", "r") as f:
            self.npc_voices = json.load(f)
        with open("assets/npc_avatars.json", "r") as f:
            self.avatar_paths = json.load(f)
        with open("assets/players.json", "r") as f:
            self.players = json.load(f)
        with open("assets/token_locations.json", "r") as f:
            self.token_locations = json.load(f)

        self.load_all_maps()
        self.active_player = self.players[0]
        self.character_sheet = CharacterSheet(self.active_player["character_file"])
        self.current_map = "sword_coast"
        self.current_node = "candlekeep"
        self.current_map = "Candlekeep"
        self.current_node = "courtyard"
        self.is_speaking = False
        self.init_ui()
        self.load_session()
        self.listening = True
        self.start_listening()

    def init_ui(self):
        self.setWindowTitle("Fantasy DM Assistant (Multi-Player)")
        self.setGeometry(100, 100, 600, 500)
        layout = QVBoxLayout()

        self.output_area = QTextBrowser()
        self.output_area.setOpenExternalLinks(True)
        layout.addWidget(QLabel("Story Log:"))
        layout.addWidget(self.output_area)

        self.input_line = QLineEdit()
        self.input_line.setPlaceholderText("What do you do?")
        layout.addWidget(self.input_line)

        self.active_player_label = QLabel(f"🎮 Active Player: {self.active_player['name']}")
        layout.addWidget(self.active_player_label)

        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self.send_input_from_text)
        self.save_button = QPushButton("Save Session")
        self.save_button.clicked.connect(self.save_session)
        self.load_button = QPushButton("Load Session")
        self.load_button.clicked.connect(self.load_session_dialog)
        self.edit_char_button = QPushButton("Edit Character")
        self.edit_char_button.clicked.connect(self.open_character_editor)
        self.switch_button = QPushButton("Switch Player")
        self.switch_button.clicked.connect(self.cycle_player)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.send_button)
        button_layout.addWidget(self.switch_button)
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.load_button)
        layout.addLayout(button_layout)
        button_layout.addWidget(self.edit_char_button)
        cs = self.character_sheet.data
        layout.addWidget(QLabel(f"Character: {cs['name']} ({cs['class']} - Level {cs['level']})"))
        layout.addWidget(QLabel(f"HP: {cs['hit_points']}  |  AC: {cs['armor_class']}  |  Spell Slots (1st): {cs['spell_slots']['1st']}"))
        self.setLayout(layout)


    def load_all_maps(self):
        self.maps = {}
        map_files = glob.glob(os.path.join("assets/maps", "*.json"))

        for file_path in map_files:
            try:
                with open(file_path, "r") as f:
                    region = json.load(f)
                    area_name = region.get("area")
                    if not area_name:
                        print(f"[Skipping map: no 'area' defined] → {file_path}")
                        continue
                    self.maps[area_name] = region
                    print(f"[Loaded map: {area_name}]")
            except Exception as e:
                print(f"[Failed to load map {file_path}: {e}]")


    def cycle_player(self):
        idx = self.players.index(self.active_player)
        idx = (idx + 1) % len(self.players)
        self.switch_to_player(self.players[idx]["name"])

    def switch_to_player(self, name):
        for player in self.players:
            if player["name"].lower() == name.lower():
                self.active_player = player
                self.character_sheet = CharacterSheet(player["character_file"])
                self.active_player_label.setText(f"🎮 Active Player: {player['name']}")
                self.safe_append(f"[Switched to {player['name']}]")
                asyncio.run(self.speak_confirmation(player["name"], player["voice"]))
                return
        self.safe_append(f"[Player '{name}' not found.]")


    def open_character_editor(self):
        self.char_editor = CharacterSheetEditor(self.character_sheet)
        self.char_editor.setWindowModality(Qt.NonModal)
        self.char_editor.show()

    def safe_append_html(self, html):
        try:
            QMetaObject.invokeMethod(self.output_area, "append", Qt.QueuedConnection, Q_ARG(str, html))
        except Exception as e:
            print(f"Failed to queue HTML append: {e}")

    def append_avatar_message(self, speaker, message):
        avatar_path = self.avatar_paths.get(speaker)
        if not avatar_path or not os.path.exists(avatar_path):
            self.safe_append(f"{speaker}: {message}")
            return
        html = f"""
        <table>
            <tr>
                <td width="64"><img src="{avatar_path}" width="48" height="48"></td>
                <td><b>{speaker}:</b> {message}</td>
            </tr>
        </table>
        """
        self.safe_append_html(html)

    def load_session_dialog(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Load Session", "", "JSON Files (*.json)")
        if file_name:
            try:
                with open(file_name, 'r') as f:
                    self.conversation_history = json.load(f)
                self.output_area.clear()
                for msg in self.conversation_history:
                    if msg['role'] == 'user':
                        self.safe_append("You: " + msg['content'])
                    elif msg['role'] == 'assistant':
                        self.safe_append("DM: " + msg['content'])
            except Exception as e:
                self.safe_append(f"[Failed to load selected session: {e}]\\n")



    def save_session(self):
        try:
            with open(SAVE_FILE, "w") as f:
                json.dump(self.conversation_history, f, indent=2)
            self.safe_append("[Session saved]")
        except Exception as e:
            self.safe_append(f"[Error saving session: {e}]")

    async def speak_confirmation(self, name, voice):
        text = f"Now speaking as {name}"
        await self.speak(text, voice=voice)

    def send_input_from_text(self):
        user_text = self.input_line.text().strip()
        self.input_line.clear()
        self.send_input(user_text)

    def inject_location_context(self):
        region = self.maps.get(self.current_map)
        node = next((n for n in region["nodes"] if n["id"] == self.current_node), None)
        if not region or not node:
            return

        context_lines = []

        # 📍 Area and label
        context_lines.append(f"You are in {region['area']} → {node['label']}.")

        # 🔁 Connected nodes
        connected = [n["label"] for n in region["nodes"] if n["id"] != self.current_node]
        context_lines.append(f"Connected locations: {', '.join(connected)}.")

        # 🧑‍🤝‍🧑 NPCs
        if node.get("npcs"):
            context_lines.append("NPCs in this area:")
            for npc in node["npcs"]:
                context_lines.append(f"- {npc['name']} ({npc['role']}): {npc['dialogue']}")

        # 🧰 Items
        if node.get("items"):
            context_lines.append("Items visible here:")
            for item in node["items"]:
                context_lines.append(f"- {item['name']} ({item['type']})")

        # 📖 Plot hooks
        if "plot" in node and "reveal" in node["plot"]:
            context_lines.append(f"Plot detail: {node['plot']['reveal']}")

        combined_context = "[Location Context]\n" + "\n".join(context_lines)
        self.conversation_history.append({"role": "system", "content": combined_context})


    def send_input(self, user_text):
        if not user_text:
            return

        lower = user_text.lower().strip()

        # 🎮 Voice-based player switching
        for player in self.players:
            name = player["name"].lower()
            if lower.startswith(f"switch to {name}") or lower.startswith(f"i am {name}") or lower.startswith(f"let {name} speak"):
                self.switch_to_player(player["name"])
                return

        # 🧙 Append player message to log
        speaker = self.character_sheet.data.get("name", "Player")
        self.append_avatar_message(speaker, user_text)
        self.conversation_history.append({"role": "user", "content": user_text})

        if lower == "skip intro":
            self.skip_intro = True
            self.safe_append("[Intro skipped]")
            return

        try:
            # 🤖 GPT request
            #    model="gpt-4-turbo",  # upgrade to turbo
            inject_tag_instruction(self.conversation_history)
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",  # upgrade to turbo
                messages=self.conversation_history
            )
            self.conversation_history = [
                msg for msg in self.conversation_history
                if "IMPORTANT: If your response involves an action" not in msg.get("content", "")
            ]
            message = run_hybrid_engine(user_text, self.conversation_history, client)
            self.conversation_history.append({"role": "assistant", "content": message})

            state_tag_match = re.findall(r"<<state:([a-zA-Z0-9_]+)=([a-zA-Z0-9_]+)>>", message)
            for key, val in state_tag_match:
                self.set_node_state(self.current_map, self.current_node, key, val == "True")
                message = message.replace(f"<<state:{key}={val}>>", "")

            cutscene_match = re.search(r"<<cutscene:(.*?)>>", message)
            if cutscene_match:
                cutscene_id = cutscene_match.group(1)
                self.trigger_cutscene(cutscene_id)
                message = message.replace(f"<<cutscene:{cutscene_id}>>", "").strip()

            # 🎭 Process DM commands in response
            # -- movement --
            print(">>>\n" + message + "\n")
            move_match = re.search(r"<<move:(.*?)>>", message)
            if move_match:
                location_id = move_match.group(1)
                self.safe_append(f"[DM moves you to {location_id}]")
                self.move_to_node(location_id)
                scene_tokens = self.token_locations.get(self.current_map, {})
                token_coords = scene_tokens.get(location_id)

                if token_coords:
                    x, y = token_coords
                    print(f"[📤] Sending move_token → {self.active_player['name']} in {self.current_map} to ({x}, {y})")
                    asyncio.run(self.foundry.move_token(
                    self.active_player["name"],
                    self.current_map,
                    x, y
                    ))
                else:
                    print(f"[⚠️] No token_coords found for '{location_id}' in '{self.current_map}'")
                    message = message.replace(f"<<move:{location_id}>>", "").strip()
                    print(f"[📤] Sending move_token")


            # -- event trigger --
            event_match = re.search(r"<<event:(.*?)>>", message)
            if event_match:
                event_id = event_match.group(1)
                self.trigger_event_by_id(event_id)
                message = message.replace(f"<<event:{event_id}>>", "").strip()

            # -- skill check --
            skill_match = re.search(r"<<skillcheck:(.*?) DC=(\\d+)>>", message)
            if skill_match:
                skill = skill_match.group(1)
                dc = int(skill_match.group(2))
                self.handle_skillcheck(skill, dc)
                message = re.sub(r"<<skillcheck:.*? DC=\d+>>", "", message).strip()

            # 🧠 Detect speaker (optional)
            detected_speaker = None
            first_line = message.strip().splitlines()[0] if message.strip() else ""
            for npc in self.npc_voices:
                if first_line.startswith(f"{npc}:"):
                    detected_speaker = npc
                    break

            # 🗣️ Display & speak result
            if detected_speaker:
                self.append_avatar_message(detected_speaker, message)
                voice = self.npc_voices.get(detected_speaker, "en-GB-RyanNeural")
            else:
                self.safe_append("DM: " + message)
                voice = "en-GB-RyanNeural"

            asyncio.run(self.speak(message, voice=voice))

        except Exception as e:
            self.safe_append(f"[Error communicating with API: {e}]")

    def trigger_cutscene(self, cutscene_id):
        if cutscene_id == "gorion_death":
            narration = [
                "The night is still and cold as Gorion leads you beyond Candlekeep’s gates.",
                "His voice is tight, his eyes scanning the dark horizon.",
                "You travel only a short while before the ambush comes.",
                "A towering armoured figure demands Gorion hand you over.",
                "Gorion refuses. Magic explodes in the darkness.",
                "You flee, as he commanded... and hear his final cry echo into the night."
            ]
            for line in narration:
                self.safe_append(f"🎬 {line}")
                cleaned_message = self.clean_for_tts(line)
                asyncio.run(self.speak(cleaned_message, voice="en-GB-RyanNeural"))
            # Optional: change location/state after cutscene
            self.move_to_node("wilderness_ambush_site")
            self.set_node_state(self.current_map, self.current_node, "gorion_dead", True)


    def handle_skillcheck(self, skill, dc):
        char = self.character_sheet.data
        mod = char.get("skills", {}).get(skill, 0)
        roll = random.randint(1, 20)
        total = roll + mod
        result_text = f"🎲 Skill Check: {skill.title()} (DC {dc}) → You rolled {roll} + {mod} = {total} → {'✅ Success!' if total >= dc else '❌ Failure.'}"
        self.safe_append(result_text)
        asyncio.run(self.speak(result_text, voice="en-GB-RyanNeural"))

    def move_player_to_label(self, label_text, voice_narration=True):
        node_id = self.find_node_id_by_label(label_text)
        if node_id:
            self.move_to_node(node_id)
            if voice_narration:
                asyncio.run(self.speak(f"You arrive at the {label_text}.", voice="en-GB-RyanNeural"))
            return True
        else:
            self.safe_append(f"[DM attempted to move you to unknown location: {label_text}]")
            return False

    def describe_current_location(self):
        node = next((n for n in self.maps[self.current_map]["nodes"] if n["id"] == self.current_node), None)
        if not node:
            self.safe_append("[Unknown location]")
            return
        desc_text = f"{node['label']}: {node['desc']}"
        self.safe_append(f"📍 {desc_text}")
        asyncio.run(self.speak(desc_text, voice="en-GB-RyanNeural"))

        for npc in node.get("npcs", []):
            self.safe_append(f"👤 {npc['name']} ({npc['role']}): \"{npc['dialogue']}\"")
        for item in node.get("items", []):
            self.safe_append(f"🧰 Item: {item['name']} ({item['type']})")

        if "plot" in node:
            if "reveal" in node["plot"]:
                self.safe_append(f"\n📖 {node['plot']['reveal']}\n")
            if "chapter_intro" in node["plot"]:
                chapter_id = node["plot"].get("progress")
                if not hasattr(self, "visited_chapters"):
                    self.visited_chapters = set()
                if chapter_id and chapter_id not in self.visited_chapters:
                    self.visited_chapters.add(chapter_id)
                    intro = node["plot"]["chapter_intro"]
                    self.safe_append(f"\n🎬 <b>{intro}</b>\n")
                    cleaned_message = self.clean_for_tts(intro)
                    asyncio.run(self.speak(cleaned_message, voice="en-GB-GuyNeural"))

    def load_session(self):
        self.skip_intro = False
        if os.path.exists(SAVE_FILE):
            with open(SAVE_FILE, 'r') as f:
                self.conversation_history = json.load(f)
            for msg in self.conversation_history:
                if msg['role'] == 'user':
                    self.safe_append("You: " + msg['content'])
                elif msg['role'] == 'assistant':
                    self.safe_append("DM: " + msg['content'])
        else:
            intro = (
                f"You are the Dungeon Master for '{self.campaign['title']}' set in {self.campaign['world']['name']}'. "
                "You are in full control of the world’s description, pacing, dialogue, and dramatic flow. "
                "Speak immersively and cinematically, evoking emotion, mystery, and tension. "
                "Your role is to narrate, adjudicate, and drive the story forward moment by moment.\n\n"

                "Players may describe their actions, but you must decide what succeeds and what fails. "
                "Use vivid language, voice character dialogue naturally, and maintain continuity across scenes.\n\n"

                "All descriptions and dialogue should sound natural and immersive. Use the tags seamlessly.\n\n"

                "You are currently inside Candlekeep, a fortress-library of great renown. The party begins here. "
                "Ensure consistency in location, character presence, and tone."
            )

        self.conversation_history = [
            {"role": "system", "content": intro},
            {"role": "user", "content": "I stand quietly in Candlekeep’s courtyard, gathering my thoughts."}
        ]
        self.safe_append("DM: The morning light filters through Candlekeep’s high walls as you prepare for the day...")

        # ✅ Narrated summary + recap
        if not self.skip_intro:
            summary = self.campaign.get("summary")
            if summary:
                self.safe_append(f"\n<b>🎞 Campaign:</b>\n{summary}\n")
                cleaned_message = self.clean_for_tts(summary)
                asyncio.run(self.speak(cleaned_message, voice="en-GB-RyanNeural"))

            recap = self.campaign.get("recap")
            if recap:
                self.safe_append(f"\n<b>🧙 Previously...</b>\n{recap}\n")
                cleaned_message = self.clean_for_tts(recap)
                asyncio.run(self.speak(cleaned_message, voice="en-GB-RyanNeural"))


        cleaned_message = self.clean_for_tts(self.conversation_history[-1]['content'])
        asyncio.run(self.speak(cleaned_message))

        # ✅ Always show current location after loading
        self.describe_current_location()

    def clean_for_tts(self, text):
        # Replace problematic characters and markdown
        replacements = {
            "*": "",  # remove asterisks (used for emphasis)
            "—": "-",  # replace em dash
            "–": "-",  # replace en dash
            "“": "\"", "”": "\"",
            "‘": "'", "’": "'",
            "…": "...",
            "•": "-",
            "\u202f": " ",  # narrow space
            "\u00a0": " ",  # non-breaking space
        }
        for bad, good in replacements.items():
            text = text.replace(bad, good)

        # Remove any hidden markdown-style formatting
        text = re.sub(r"[*_~`#^]+", "", text)

        # Strip emojis and non-ASCII characters (optional)
        text = ''.join(c for c in text if ord(c) < 128)

        return text


    async def speak(self, text, voice="en-GB-RyanNeural"):
        try:
            if not text.strip():
                print("TTS: Skipping empty input.")
                return
            self.is_speaking = True
            filename = f"response_{uuid.uuid4().hex}.mp3"
            print(f"TTS: Speaking with voice {voice}: {text[:60]}...")
            communicate = edge_tts.Communicate(text, voice=voice)
            await communicate.save(filename)
            play_tts_audio(filename)
            if os.path.exists(filename):
                os.remove(filename)
        except Exception as e:
            print(f"TTS error: {e}")
        finally:
            self.is_speaking = False


    def load_region(self, region_file):
        path = os.path.join("assets/maps", region_file)
        try:
            with open(path, "r") as f:
                region = json.load(f)
            area = region["area"]
            self.maps[area] = region
            self.current_map = area
            self.current_node = region["nodes"][0]["id"]
            self.safe_append(f"[Entering {area}]")
            self.describe_current_location()
        except Exception as e:
            self.safe_append(f"[Failed to load region: {e}]")

    def find_node_id_by_label(self, label_text):
        label_text = label_text.lower().strip()
        current_region = self.maps.get(self.current_map)
        if not current_region:
            return None
        for node in current_region["nodes"]:
            if node["label"].lower() == label_text:
                return node["id"]
        return None

    def list_available_nodes(self):
        region = self.maps.get(self.current_map)
        if not region:
            self.safe_append("[No current map loaded.]")
            return
        names = [n["label"] for n in region["nodes"]]
        self.safe_append("You can travel to: " + ", ".join(names))

    def move_to_node(self, target_node_id):
        region_map = self.maps.get(self.current_map)
        if not region_map:
            self.safe_append("[Unknown map]")
            return

        for node in region_map["nodes"]:
            if node["id"] == target_node_id:
                self.current_node = node["id"]

                # 🧠 Inject canonical room description
                label = node.get("label", "Unknown Area")
                desc = node.get("desc", "")
                room_context = (
                    f"[You are in {label}. This area is canonically described as: \"{desc}\". "
                    "Use this for consistent narration unless the area has changed.]"
                )
                self.conversation_history.append({"role": "system", "content": room_context})

                # 🧠 Inject current environmental state
                state = self.get_node_state(self.current_map, self.current_node)
                if state:
                    state_text = "; ".join(f"{k} = {v}" for k, v in state.items())
                    state_context = f"[Current known state of this area: {state_text}]"
                    self.conversation_history.append({"role": "system", "content": state_context})

                # 🧠 Inject world/map/NPC/item context
                self.inject_location_context()

                return

        # Check for linked region from world map
        if self.current_map == "sword_coast":
            for node in region_map["nodes"]:
                if node["id"] == target_node_id:
                    new_region_file = node.get("region")
                    if new_region_file:
                        self.load_region(new_region_file)
                        return

        self.safe_append(f"[Can't find location '{target_node_id}']")


    def load_environment_state(self):
        if os.path.exists(ENV_STATE_FILE):
            with open(ENV_STATE_FILE, "r") as f:
                self.environment_state = json.load(f)
        else:
            self.environment_state = {}

    def save_environment_state(self):
        os.makedirs(os.path.dirname(ENV_STATE_FILE), exist_ok=True)
        with open(ENV_STATE_FILE, "w") as f:
            json.dump(self.environment_state, f, indent=2)

    def get_node_state(self, map_name, node_id):
        return self.environment_state.get(f"{map_name}/{node_id}", {})

    def set_node_state(self, map_name, node_id, key, value=True):
        full_id = f"{map_name}/{node_id}"
        if full_id not in self.environment_state:
            self.environment_state[full_id] = {}
        self.environment_state[full_id][key] = value
        self.save_environment_state()


    def safe_append(self, text):
        try:
            QMetaObject.invokeMethod(
                self.output_area,
                "append",
                Qt.QueuedConnection,
                Q_ARG(str, text)
            )
        except Exception as e:
            print(f"[UI append error]: {e}")

    def start_listening(self):
        def listen():
            with mic as source:
                recogniser.adjust_for_ambient_noise(source, duration=1)
                while self.listening:
                    if self.is_speaking:
                        continue  # Skip listening while TTS is active
                    try:
                        print("Listening...")
                        audio = recogniser.listen(source, timeout=5, phrase_time_limit=8)
                        user_text = recogniser.recognize_google(audio)
                        print(f"Recognised: {user_text}")
                        self.safe_append(f"🎤 Recognised: {user_text}")
                        self.send_input(user_text)
                    except sr.WaitTimeoutError:
                        continue
                    except sr.UnknownValueError:
                        continue
                    except Exception as e:
                        print(f"Error in recognition: {e}")

        threading.Thread(target=listen, daemon=True).start()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DMApp()
    window.show()
    sys.exit(app.exec_())
