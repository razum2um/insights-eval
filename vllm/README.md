# Running the eval against vLLM

The stock Gemma chat template doesn't render a `tools` block, so the
model emits a non-standard `call:name{args}` format that no vLLM
tool-call parser can read. `gemma_tools_chat_template.jinja` fixes that:
it renders the tools into the prompt and instructs the model to emit
JSON tool calls in `<tool_call>...</tool_call>` tags — the format the
`hermes` parser extracts. JSON (not `pythonic`) is used deliberately:
this eval passes 1024+ char `user_intent` strings and multi-line SQL,
which need real string escaping.

## Relaunch vLLM

Copy the template to the server, then add these flags:

```bash
scp vllm/gemma_tools_chat_template.jinja au.razum2um.dev:/path/to/

python -m vllm.entrypoints.openai.api_server \
  --model cyankiwi/gemma-4-26B-A4B-it-AWQ-4bit \
  ... your existing flags ... \
  --enable-auto-tool-choice \
  --tool-call-parser hermes \
  --chat-template /path/to/gemma_tools_chat_template.jinja \
  --max-num-seqs 16
```

- Change `--tool-call-parser pythonic` → `hermes`.
- `--max-num-seqs 16` lets vLLM batch concurrent requests. Without it the
  server processes one sequence at a time and a 15-sample agentic run is
  fully serialized (hours instead of ~30-45 min).

## Verify

A probe should now return a populated `tool_calls` array:

```bash
curl -s http://au.razum2um.dev:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"cyankiwi/gemma-4-26B-A4B-it-AWQ-4bit",
       "messages":[{"role":"user","content":"Weather in Paris? Use the tool."}],
       "tools":[{"type":"function","function":{"name":"get_weather",
         "description":"Get weather","parameters":{"type":"object",
         "properties":{"city":{"type":"string"}},"required":["city"]}}}],
       "tool_choice":"auto"}'
```

## Run the eval

```bash
export VLLM_BASE_URL=http://au.razum2um.dev:8000/v1
export VLLM_API_KEY=dummy        # vLLM ignores it unless --api-key was set
make eval MODEL=openai-api/vllm/cyankiwi/gemma-4-26B-A4B-it-AWQ-4bit
```
