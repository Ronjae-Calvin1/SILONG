import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { LandingPage } from "./pages/LandingPage";
import { MapPage } from "./pages/MapPage";
import { AdminSignInPage } from "./pages/AdminSignInPage";

// "/" is the landing page (approved addition); "Get Started" opens the map at "/map".
// "/admin" is where the menu's "Admin sign in" goes.
// Any other address goes back to the landing page.
function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/map" element={<MapPage />} />
        <Route path="/admin" element={<AdminSignInPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;