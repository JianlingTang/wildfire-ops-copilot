"use client";

import { initializeApp, getApps } from "firebase/app";
import { getAuth, signInAnonymously } from "firebase/auth";

const firebaseConfig = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID
};

const isFirebaseConfigured = Boolean(
  firebaseConfig.apiKey && firebaseConfig.authDomain && firebaseConfig.projectId && firebaseConfig.appId
);

let tokenPromise: Promise<string | null> | null = null;

export async function getFirebaseIdToken(): Promise<string | null> {
  if (!isFirebaseConfigured) {
    return null;
  }
  tokenPromise ??= getFreshFirebaseIdToken();
  return tokenPromise;
}

async function getFreshFirebaseIdToken(): Promise<string | null> {
  const app = getApps()[0] ?? initializeApp(firebaseConfig);
  const auth = getAuth(app);
  const userCredential = auth.currentUser ? null : await signInAnonymously(auth);
  const user = auth.currentUser ?? userCredential?.user;
  return user ? user.getIdToken() : null;
}
