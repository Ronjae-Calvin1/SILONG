import { useAuth } from "../auth";

export default function SignedOutPage() {
  const { goToSignIn, expiredDetail } = useAuth();
  return (
    <main className="signin">
      <div className="signin-card signedout" role="alert">
        <h1>You were signed out</h1>
        <p>Admin accounts sign out after 30 minutes without use. Sign in again to keep working.</p>
        {expiredDetail && <p className="signin-sub">{expiredDetail}</p>}
        <button className="btn btn-primary signin-submit" onClick={goToSignIn}>
          Sign in
        </button>
      </div>
    </main>
  );
}
