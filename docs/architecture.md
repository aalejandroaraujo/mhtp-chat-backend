```mermaid
graph TD
  A[Typebot] --> B(Assistant Intake)
  B -->|evaluate_intake_progress| C(Function 1)
  B --> D(Assistant Advice)
  D -->|risk_escalation_check| E(Function 2)
  D -->|switch_chat_mode| F(Function 3)
  D --> G(Assistant Summary)
  G -->|save_session_summary| H(Function 4)
  H --> I[NocoDB REST]
```

The monolithic FastAPI layer was removed. Each tool is now an Azure Function
invoked directly by the OpenAI Assistant runtime. They share small utilities
for OpenAI and NocoDB access but otherwise run independently.
