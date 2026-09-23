import { approveTestPayment, completeTestPayment, setSessionToken, verifyPiAccessToken } from "./api";

let piSdkPromise;

export function loadPiSdk() {
  if (window.Pi) return Promise.resolve(initPi());
  if (piSdkPromise) return piSdkPromise;
  piSdkPromise = new Promise((resolve) => {
    const script = document.createElement("script");
    script.src = "https://sdk.minepi.com/pi-sdk.js";
    script.async = true;
    script.onload = () => resolve(initPi());
    script.onerror = () => resolve(false);
    document.head.appendChild(script);
  });
  return piSdkPromise;
}

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
  const incomplete = [];
  const auth = await window.Pi.authenticate(["username", "payments"], (payment) => {
    if (payment?.identifier && payment?.transaction?.txid) incomplete.push(payment);
  });
  const verified = await verifyPiAccessToken(auth.accessToken);
  for (const payment of incomplete) {
    await completeTestPayment(payment.identifier, payment.transaction.txid);
  }
  return {
    username: verified.username,
    role: verified.role,
    verified: true,
    demo: false
  };
}

export function startTestPayment(onStatus) {
  if (!window.Pi || !window.Pi.createPayment) throw new Error("Hãy mở Trace AI trong Pi Browser.");
  window.Pi.createPayment({
    amount: 0.01,
    memo: "Trace AI - Testnet payment test",
    metadata: { purpose: "trace_ai_test" },
  }, {
    onReadyForServerApproval: async (paymentId) => {
      await approveTestPayment(paymentId);
      onStatus("Đã duyệt giao dịch. Xác nhận trong ví Pi.");
    },
    onReadyForServerCompletion: async (paymentId, txid) => {
      await completeTestPayment(paymentId, txid);
      onStatus("Giao dịch thử đã hoàn tất.");
    },
    onCancel: () => onStatus("Bạn đã hủy giao dịch thử."),
    onError: (error) => onStatus(error?.message || "Không thể hoàn tất giao dịch."),
  });
}
