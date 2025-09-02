import express from "express";
import fetch from "node-fetch";
import dotenv from "dotenv";
import cors from "cors";
import crypto from "crypto";

dotenv.config();

const app = express();
app.use(cors());
app.use(express.json());

// ----------------- CHATBOT ROUTE (your default) -----------------
app.post("/api/chat", async (req, res) => {
  try {
    const { messages } = req.body;

    const response = await fetch("https://api.groq.com/openai/v1/chat/completions", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${process.env.GROQ_API_KEY}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: "llama-3.1-8b-instant",
        messages,
      }),
    });

    const data = await response.json();
    res.json(data);
  } catch (err) {
    console.error("Server error:", err);
    res.status(500).json({ error: "Something went wrong." });
  }
});

// ----------------- ONE PERSON VERIFICATION LOGIC -----------------
let activeUser = null; // Only one person can verify at a time
const otpStore = {};   // { aadhar: {otp, verified}, pan: {...}, dl: {...} }

// Middleware to lock one user
app.use((req, res, next) => {
  if (!activeUser) {
    activeUser = req.ip; // Assign first user by IP
  }
  if (req.ip !== activeUser) {
    return res.status(403).json({ error: "Verification locked. Only one person allowed at a time." });
  }
  next();
});

// ----------------- Generate OTP -----------------
function generateOTP() {
  return crypto.randomInt(100000, 999999).toString();
}

// ----------------- Aadhaar Verification -----------------
app.post("/api/verify/aadhar", (req, res) => {
  const { aadharNumber } = req.body;
  if (!aadharNumber || aadharNumber.length !== 12) {
    return res.status(400).json({ error: "Invalid Aadhaar number" });
  }

  const otp = generateOTP();
  otpStore.aadhar = { otp, verified: false };
  console.log(`📩 Aadhaar OTP for ${aadharNumber}: ${otp}`);
  res.json({ message: "OTP sent for Aadhaar verification" });
});

app.post("/api/verify/aadhar/otp", (req, res) => {
  const { otp } = req.body;
  if (otpStore.aadhar && otpStore.aadhar.otp === otp) {
    otpStore.aadhar.verified = true;
    return res.json({ message: "Aadhaar verified successfully ✅" });
  }
  res.status(400).json({ error: "Invalid OTP for Aadhaar ❌" });
});

// ----------------- PAN Verification -----------------
app.post("/api/verify/pan", (req, res) => {
  const { panNumber } = req.body;
  if (!panNumber || panNumber.length !== 10) {
    return res.status(400).json({ error: "Invalid PAN number" });
  }

  const otp = generateOTP();
  otpStore.pan = { otp, verified: false };
  console.log(`📩 PAN OTP for ${panNumber}: ${otp}`);
  res.json({ message: "OTP sent for PAN verification" });
});

app.post("/api/verify/pan/otp", (req, res) => {
  const { otp } = req.body;
  if (otpStore.pan && otpStore.pan.otp === otp) {
    otpStore.pan.verified = true;
    return res.json({ message: "PAN verified successfully ✅" });
  }
  res.status(400).json({ error: "Invalid OTP for PAN ❌" });
});

// ----------------- Driving License Verification -----------------
app.post("/api/verify/dl", (req, res) => {
  const { dlNumber } = req.body;
  if (!dlNumber || dlNumber.length < 8) {
    return res.status(400).json({ error: "Invalid Driving License number" });
  }

  const otp = generateOTP();
  otpStore.dl = { otp, verified: false };
  console.log(`📩 DL OTP for ${dlNumber}: ${otp}`);
  res.json({ message: "OTP sent for Driving License verification" });
});

app.post("/api/verify/dl/otp", (req, res) => {
  const { otp } = req.body;
  if (otpStore.dl && otpStore.dl.otp === otp) {
    otpStore.dl.verified = true;
    return res.json({ message: "Driving License verified successfully ✅" });
  }
  res.status(400).json({ error: "Invalid OTP for Driving License ❌" });
});

// ----------------- Reset (after one person is done) -----------------
app.post("/api/reset-verification", (req, res) => {
  activeUser = null;
  for (let key in otpStore) delete otpStore[key];
  res.json({ message: "Verification system reset. Next person can verify now." });
});

// ----------------- START SERVER -----------------
const PORT = process.env.PORT || 5000;
app.listen(PORT, () => console.log(`✅ Server running on port ${PORT}`));
