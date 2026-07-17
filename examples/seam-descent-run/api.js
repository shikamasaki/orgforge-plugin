'use strict';

// Thin command layer: pure dispatch over a passed-in store.
// No I/O, no argv, no printing. Returns plain result objects.
// Never throws for normal cases (missing id -> ok:false).

function handle(store, cmd) {
  switch (cmd.op) {
    case 'add': {
      const task = store.add(cmd.text);
      return { ok: true, op: 'add', task };
    }
    case 'toggle': {
      const task = store.toggle(cmd.id);
      if (task == null) {
        return { ok: false, op: 'toggle', error: 'not found' };
      }
      return { ok: true, op: 'toggle', task };
    }
    case 'remove': {
      const removed = store.remove(cmd.id);
      return { ok: true, op: 'remove', removed };
    }
    case 'list': {
      return { ok: true, op: 'list', tasks: store.all() };
    }
    default:
      return { ok: false, error: 'unknown op: ' + cmd.op };
  }
}

module.exports = { handle };
