# Verification: 001 — Agent Runtime Functional

## Automated Tests

### Unit Tests

```python
# tests/unit/test_config.py
def test_settings_loads_from_env():
    ...

def test_settings_validates_required_fields():
    ...

# tests/unit/test_instructions.py
def test_loads_all_prompt_files():
    ...

def test_assembles_instructions_without_errors():
    ...

# tests/unit/test_system_tools.py
def test_get_current_datetime_returns_iso_format():
    ...

def test_get_current_datetime_is_current():
    ...
```

### Integration Tests

```python
# tests/integration/test_agent_creation.py
def test_agent_initializes_with_all_components():
    ...

def test_tool_is_registered():
    ...

# tests/integration/test_llm_factory.py
def test_creates_openai_model():
    ...
```

## Manual E2E Tests

### E2E-001: Basic Conversation
```
User (Telegram): Hola
Agent: ¡Hola! Soy AncoraMind, tu asistente personal. ¿En qué puedo ayudarte?
```

### E2E-002: Tool Selection
```
User: ¿Qué hora es?
Agent calls: get_current_datetime()
Agent: Son las 15:42 del 23 de agosto de 2026.  ← (or similar, in Spanish)
```

### E2E-003: Context Maintenance
```
User: Me llamo Juan.
Agent: Encantado, Juan.

User: ¿Cómo me llamo?
Agent: Te llamas Juan.
```

### E2E-004: Non-Tool Question
```
User: ¿Cuál es la capital de Francia?
Agent: París.
```
(Should NOT call any tool)

### E2E-005: Spanish Default
```
User: What's your name?
Agent: Me llamo AncoraMind.  ← (responds in Spanish by default per channel policy)
```

## Acceptance Criteria

- [ ] User can send a message from Telegram and receive a coherent response
- [ ] `get_current_datetime` tool is called and returns correct time
- [ ] Multi-turn conversation maintains context
- [ ] Agent does not call tools for non-tool questions
- [ ] Agent responds in Spanish by default
- [ ] Non-private chats are rejected
- [ ] Non-allowlisted users are rejected
- [ ] Application starts successfully via Docker Compose