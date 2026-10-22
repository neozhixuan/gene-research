#!/usr/bin/env bash
# UserPromptSubmit hook: if data sources the pipeline wants are still blocked by the
# cloud environment's network policy, remind the user to allowlist them.
# Prints nothing once every host is reachable, so the reminder stops by itself.
hosts=(www.reddit.com api.stocktwits.com data.sec.gov www.sec.gov www.cnbc.com)
blocked=()
for h in "${hosts[@]}"; do
  code=$(curl -s -o /dev/null -m 4 -w '%{http_code}' -A 'gene-research' "https://$h/" 2>/dev/null)
  [ "$code" = "000" ] && blocked+=("$h")
done
[ ${#blocked[@]} -eq 0 ] && exit 0
list=$(IFS=,; echo "${blocked[*]}" | sed 's/,/, /g')
msg="Still blocked by the cloud environment's network policy: $list. Add them under the environment's Network access > Allowed domains (https://code.claude.com/docs/en/cloud-environments#network-access); new sessions pick it up."
printf '{"systemMessage": %s, "hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": %s}}\n' \
  "$(printf '%s' "Reminder: $msg" | python3 -c 'import json,sys;print(json.dumps(sys.stdin.read()))')" \
  "$(printf '%s' "Remind the user in one line at the end of your reply: $msg" | python3 -c 'import json,sys;print(json.dumps(sys.stdin.read()))')"
