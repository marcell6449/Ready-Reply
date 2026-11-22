// Small shared state for the signed-in session.

export const state = {
  me: null,
  query: "",
  variables: [],
  pendingQuestion: null,
};

export function isAdmin() {
  return state.me?.role === "admin";
}
