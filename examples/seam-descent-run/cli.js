'use strict';

// Entry point. The only layer that touches process.argv and stdout.
// No business logic here: parse argv -> cmd, wire the real store + api,
// then render handle()'s result in human-readable form.

const { createStore } = require('./store.js');
const { handle } = require('./api.js');

function buildCmd(op, arg) {
  switch (op) {
    case 'add':
      return { op: 'add', text: arg };
    case 'toggle':
      return { op: 'toggle', id: arg };
    case 'remove':
      return { op: 'remove', id: arg };
    case 'list':
      return { op: 'list' };
    default:
      // Let the api layer decide what "unknown op" means.
      return { op: op };
  }
}

function formatTask(t) {
  const box = t.done ? '[x]' : '[ ]';
  return box + ' ' + t.id + ' ' + t.text;
}

function render(cmd, result) {
  if (result.ok === false) {
    // Uniform error rendering for any failing command (toggle miss,
    // unknown op, etc.).
    return result.error;
  }

  switch (result.op) {
    case 'list': {
      const tasks = result.tasks;
      if (!tasks || tasks.length === 0) {
        return '(no tasks)';
      }
      return tasks.map(formatTask).join('\n');
    }
    case 'add': {
      const t = result.task;
      return 'Added: ' + t.id + ' ' + t.text;
    }
    case 'toggle': {
      const t = result.task;
      return 'Toggled: ' + t.id + ' ' + t.text + ' -> done=' + t.done;
    }
    case 'remove': {
      // The result carries only `removed`; the id came from the command.
      return result.removed ? 'Removed ' + cmd.id : 'No task ' + cmd.id;
    }
    default:
      return JSON.stringify(result);
  }
}

function main() {
  const op = process.argv[2];
  const arg = process.argv[3];

  const cmd = buildCmd(op, arg);
  const store = createStore();
  const result = handle(store, cmd);

  console.log(render(cmd, result));

  if (result.ok === false) {
    process.exitCode = 1;
  }
}

main();
