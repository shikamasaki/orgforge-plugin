'use strict';

const fs = require('fs');
const path = require('path');

const DEFAULT_PATH = path.join(__dirname, 'tasks.json');

/**
 * Create a JSON-file backed task store.
 *
 * Task shape: { id: string, text: string, done: boolean }
 *
 * @param {string} [filePath] - Path to the JSON file. Defaults to
 *   `path.join(__dirname, 'tasks.json')`.
 * @returns {{
 *   add: (text: string) => {id: string, text: string, done: boolean},
 *   toggle: (id: string) => ({id: string, text: string, done: boolean}|null),
 *   remove: (id: string) => boolean,
 *   all: () => Array<{id: string, text: string, done: boolean}>
 * }}
 */
function createStore(filePath) {
  const file = filePath || DEFAULT_PATH;

  // In-memory state loaded defensively from disk.
  let tasks = [];
  // Persisted monotonic counter so ids are unique AND stable across reloads
  // (we never re-index by array position).
  let nextId = 1;

  function load() {
    let raw;
    try {
      raw = fs.readFileSync(file, 'utf8');
    } catch (err) {
      // File absent (or unreadable) -> start empty, never crash.
      tasks = [];
      nextId = 1;
      return;
    }

    let parsed;
    try {
      parsed = JSON.parse(raw);
    } catch (err) {
      // Corrupt / unparseable -> start empty, never crash.
      tasks = [];
      nextId = 1;
      return;
    }

    // Accept the persisted envelope { tasks, nextId } and be tolerant of a
    // bare array (older/hand-edited files). Anything unexpected -> empty.
    if (Array.isArray(parsed)) {
      tasks = parsed.filter(isValidTask);
    } else if (parsed && Array.isArray(parsed.tasks)) {
      tasks = parsed.tasks.filter(isValidTask);
    } else {
      tasks = [];
    }

    // Derive a safe nextId: honor a persisted counter, but never allow it to
    // collide with an existing id, so ids stay unique across the store's life.
    let counter = 1;
    if (parsed && typeof parsed.nextId === 'number' && parsed.nextId > 0) {
      counter = Math.floor(parsed.nextId);
    }
    for (const t of tasks) {
      const n = parseInt(t.id, 10);
      if (!Number.isNaN(n) && n >= counter) {
        counter = n + 1;
      }
    }
    nextId = counter;
  }

  function isValidTask(t) {
    return (
      t &&
      typeof t === 'object' &&
      typeof t.id === 'string' &&
      typeof t.text === 'string' &&
      typeof t.done === 'boolean'
    );
  }

  function persist() {
    const payload = JSON.stringify({ tasks, nextId }, null, 2);
    fs.writeFileSync(file, payload, 'utf8');
  }

  function add(text) {
    const task = {
      id: String(nextId),
      text: text,
      done: false,
    };
    nextId += 1;
    tasks.push(task);
    persist();
    return task;
  }

  function toggle(id) {
    const task = tasks.find((t) => t.id === id);
    if (!task) {
      return null;
    }
    task.done = !task.done;
    persist();
    return task;
  }

  function remove(id) {
    const idx = tasks.findIndex((t) => t.id === id);
    if (idx === -1) {
      return false;
    }
    tasks.splice(idx, 1);
    persist();
    return true;
  }

  function all() {
    return tasks;
  }

  load();

  return { add, toggle, remove, all };
}

module.exports = { createStore };
