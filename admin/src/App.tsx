import { BrowserRouter } from "react-router-dom";
import { useAuth } from "./auth";
import AuthProvider from "./components/AuthProvider";
import Console from "./components/Console";
import SignInPage from "./pages/SignInPage";
import SignedOutPage from "./pages/SignedOutPage";

function Gate() {
  const { status } = useAuth();
  if (status === "loading") return <p className="empty">Loading…</p>;
  if (status === "expired") return <SignedOutPage />;
  if (status === "out") return <SignInPage />;
  return <Console />;
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Gate />
      </BrowserRouter>
    </AuthProvider>
  );
}
