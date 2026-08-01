import test from "node:test";
import assert from "node:assert/strict";

import {
  filterRecords,
  filterUsers,
  resolveRoute,
  sortSources,
  sourceHealthState,
  taskNeedsPolling,
} from "../../app/ui/assets/js/core/state.js";


test("resolveRoute keeps the five top-level routes and falls back to overview", () => {
  assert.equal(resolveRoute("#/users"), "users");
  assert.equal(resolveRoute("#records"), "records");
  assert.equal(resolveRoute("#/sources?type=image"), "sources");
  assert.equal(resolveRoute("#/settings"), "settings");
  assert.equal(resolveRoute("#/not-found"), "overview");
  assert.equal(resolveRoute(""), "overview");
});


test("filterUsers matches account or nickname and enabled state", () => {
  const users = [
    { username: "alice", nickname: "研发", enabled: true },
    { username: "bob", nickname: "设计", enabled: false },
  ];

  assert.deepEqual(filterUsers(users, { query: "研", status: "all" }), [users[0]]);
  assert.deepEqual(filterUsers(users, { query: "BOB", status: "disabled" }), [users[1]]);
  assert.deepEqual(filterUsers(users, { query: "", status: "enabled" }), [users[0]]);
});


test("filterRecords combines status and user filters", () => {
  const records = [
    { username: "alice", user_id: "1", success: true },
    { username: "bob", user_id: "2", success: false },
  ];

  assert.deepEqual(filterRecords(records, { status: "failure", userId: "all" }), [records[1]]);
  assert.deepEqual(filterRecords(records, { status: "all", userId: "1" }), [records[0]]);
});


test("content source health and ordering follow operational priority", () => {
  assert.equal(sourceHealthState({ consecutive_failures: 3 }), "unavailable");
  assert.equal(sourceHealthState({ consecutive_failures: 1 }), "degraded");
  assert.equal(sourceHealthState({ consecutive_failures: 0, last_success_at: "now" }), "healthy");
  assert.equal(sourceHealthState({ consecutive_failures: 0 }), "unknown");

  const sources = [
    { key: "late", priority: 30, name: "Late" },
    { key: "first", priority: 10, name: "First" },
    { key: "middle", priority: 20, name: "Middle" },
  ];
  assert.deepEqual(sortSources(sources).map((source) => source.key), ["first", "middle", "late"]);
  assert.deepEqual(sources.map((source) => source.key), ["late", "first", "middle"]);
});


test("only pending and running tasks require polling", () => {
  assert.equal(taskNeedsPolling({ status: "pending" }), true);
  assert.equal(taskNeedsPolling({ status: "running" }), true);
  assert.equal(taskNeedsPolling({ status: "completed" }), false);
  assert.equal(taskNeedsPolling(null), false);
});
