import { setSessionToken, verifyPiAccessToken } from "./api";

export function initPi() {
  if (!window.Pi) return false;
  try {
    const sandbox = String(import.meta.env.VITE_PI_SANDBOX ?? "true") === "true";
    window.Pi.init({ version: "2.0", sandbox });
    return true;
  } catch {
    return false;
  }
}

export async function authenticatePi() {
  if (!window.Pi) {
    setSessionToken("");
    return { uid: "demo-user", username: "Demo Operator", role: "admin", verified: false, demo: true };
  }
  const auth = await window.Pi.authenticate(["username"], () => {});
  const verified = await verifyPiAccessToken(auth.accessToken);
  return {
    username: verified.username,
    role: verified.role,
    verified: true,
    demo: false
  };
}
