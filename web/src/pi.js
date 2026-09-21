export function initPi() {
  if (!window.Pi) return false;
  try {
    window.Pi.init({ version: "2.0", sandbox: true });
    return true;
  } catch {
    return false;
  }
}

export async function authenticatePi() {
  if (!window.Pi) {
    return {
      uid: "demo-user",
      username: "Demo Operator",
      demo: true
    };
  }

  const scopes = ["username"];
  const auth = await window.Pi.authenticate(scopes, () => {});
  return {
    uid: auth.user.uid,
    username: auth.user.username,
    accessToken: auth.accessToken,
    demo: false
  };
}
