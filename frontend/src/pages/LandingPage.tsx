import { Link } from "react-router-dom";
import logoWhite from "../assets/silong-logo-white.png";
import "./LandingPage.css";

// First screen. "Get Started" opens the map. The menu and Emergency buttons from the
// design are added with the menu (Task 3) and the hotlines screen (Task 6), so that
// nothing on this screen is a button that does nothing.
export function LandingPage() {
  return (
    <main className="landing">
      <div className="landing-rain" aria-hidden="true" />

      <div className="landing-inner">
        <h1 className="landing-headline">When the Storm Comes, Find Your Shelter in SILONG. </h1>

        {/* Decorative: the name is already in the heading above. */}
        <img className="landing-logo" src={logoWhite} alt="" width={800} height={228} />

        <p className="landing-tagline">Your Digital Helper Before, During and After the Storm</p>

        <div className="landing-cta">
          <Link className="landing-start" to="/map">
            Get Started
          </Link>
          <p className="landing-note">No account needed</p>
        </div>
      </div>
    </main>
  );
}