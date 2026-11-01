import { Icon } from "./icons";

type Props = {
  onOpenIncident: () => void;
};

export function FloatingButtons({ onOpenIncident }: Props) {
  return (
    <div className="fab-column">
      <button
        className="fab fab-orange"
        aria-label="Submit incident report"
        onClick={onOpenIncident}
      >
        <Icon name="megaphone" />
      </button>
      <button className="fab fab-red" aria-label="Emergency calls">
        <Icon name="phone" />
      </button>
      <button className="fab fab-green" aria-label="Ask box">
        <Icon name="bot" />
      </button>
    </div>
  );
}