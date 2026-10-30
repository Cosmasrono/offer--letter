import type { Metadata } from "next";
import { AuthCard } from "@/components/AuthCard";

export const metadata: Metadata = { title: "Sign in · Offer Letter Checker" };

export default function SignInPage() {
  return <AuthCard mode="sign-in" />;
}
