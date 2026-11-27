import { useMediaQuery } from "./useMediaQuery";
import DesktopConsole from "./DesktopConsole";
import PhoneConsole from "./PhoneConsole";

// One console, two layouts: the phone layout below 768 px, the computer layout above.
export default function Console() {
  const phone = useMediaQuery("(max-width: 767px)");
  return phone ? <PhoneConsole /> : <DesktopConsole />;
}
