agent_start:
  runner.agent_stop.update:
    - agent_id: {{ data['id'] }}
