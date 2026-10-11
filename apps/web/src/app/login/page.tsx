import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { SignInForm } from "../../features/auth/sign-in-form";
import { SESSION_COOKIE, returnPath, validSession } from "../../lib/auth/session";
import { authConfigurationError } from "../../lib/auth/config";

export default async function SignInPage({ searchParams }: { searchParams: Promise<{ returnTo?: string | string[] }> }) {
  const params = await searchParams;
  const destination = returnPath(params.returnTo);
  const authenticated = validSession((await cookies()).get(SESSION_COOKIE)?.value ?? "");
  // A local workspace with no configured login must not show a form that cannot succeed.
  if (authenticated || (!process.env.SECURITY_PASSWORD && !authConfigurationError())) redirect(destination);
  return <SignInForm initialUsername={process.env.SECURITY_USERNAME ?? "healthgrid"} />;
}
