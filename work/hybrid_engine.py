import re

SYSTEM_TAGS = ["<<move:", "<<event:", "<<cutscene:", "<<state:", "<<skillcheck:"]

def has_system_tags(text):
    return any(tag in text for tag in SYSTEM_TAGS)

def user_might_trigger_tag(text):
    triggers = ["go", "enter", "walk to", "head to", "leave", "travel to", "move to", "check", "look around", "approach", "into", "exit"]
    return any(trigger in text.lower() for trigger in triggers)

def get_gpt_response(model, history, client):
    response = client.chat.completions.create(
        model=model,
        messages=history
    )
    return response.choices[0].message.content

def get_verified_response(history, client):
    # Add reminder for GPT-4
    corrected_history = history + [{
        "role": "system",
        "content": (
            "REMINDER: You MUST include system tags like <<move:location_id>>, <<event:event_id>>, "
            "<<cutscene:cutscene_id>>, <<skillcheck:skill DC=number>>, or <<state:key=value>> when relevant. "
            "These tags are invisible to the player but are REQUIRED to trigger game actions."
        )
    }]
    return get_gpt_response("gpt-4-turbo", corrected_history, client)

def run_hybrid_engine(user_input, conversation_history, client):
    print("=== GPT MESSAGES ===")
    for msg in conversation_history[-5:]:  # last few messages
        print(msg['role'].upper(), ":", msg['content'][:200])
    conversation_history.append({"role": "user", "content": user_input})

    # 🔁 Step 1: Use GPT-3.5 first
    message = get_gpt_response("gpt-3.5-turbo", conversation_history, client)
    print("[GPT-3.5] Response:", message)

    if has_system_tags(message):
        conversation_history.append({"role": "assistant", "content": message})
        return message

    # 🔎 Step 2: If suspicious input but no tag, retry with GPT-4
    if user_might_trigger_tag(user_input):
        print("[⚠️] No system tag found. Verifying with GPT-4...")
        verified = get_verified_response(conversation_history, client)
        print("[GPT-4-turbo] Response:", verified)

        # ✅ Step 3: Teach GPT-3.5 via correction
        if has_system_tags(verified):
            correction = (
                "Your last message omitted a required tag (like <<move:...>> or <<event:...>>). "
                "Whenever a system-triggering action is described, include the tag inline at the end of the sentence."
            )
            conversation_history.append({"role": "system", "content": correction})
            conversation_history.append({"role": "assistant", "content": verified})
            return verified

    # 🧯 Final fallback: use original message without tag
    conversation_history.append({"role": "assistant", "content": message})
    return message
