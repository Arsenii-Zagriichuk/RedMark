// Line icons from the RedMark interface system (24 px grid, round caps).
import type { ReactNode } from "react";

function Icon({ size, stroke, width = 1.75, children }: {
  size: number;
  stroke: string;
  width?: number;
  children: ReactNode;
}) {
  return (
    <svg
      aria-hidden="true"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke={stroke}
      strokeWidth={width}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {children}
    </svg>
  );
}

type Props = { size?: number; stroke?: string };

export const HouseIcon = ({ size = 17, stroke = "#ffffff" }: Props) => (
  <Icon size={size} stroke={stroke} width={2}>
    <path d="M3 11l9-7 9 7M5 10v10h14V10" />
  </Icon>
);

export const FlagIcon = ({ size = 16, stroke = "#f2f5fa" }: Props) => (
  <Icon size={size} stroke={stroke} width={2}>
    <path d="M5 21V4M5 4h11l-2 4 2 4H5" />
  </Icon>
);

export const SearchIcon = ({ size = 20, stroke = "#9aa6bf" }: Props) => (
  <Icon size={size} stroke={stroke} width={1.5}>
    <circle cx="11" cy="11" r="7" />
    <path d="M20 20l-4-4" />
  </Icon>
);

export const ClockIcon = ({ size = 18, stroke = "#9aa6bf" }: Props) => (
  <Icon size={size} stroke={stroke} width={1.5}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7v5l3 2" />
  </Icon>
);

export const PinIcon = ({ size = 18, stroke = "#9aa6bf" }: Props) => (
  <Icon size={size} stroke={stroke} width={1.5}>
    <path d="M12 21s-7-6.2-7-11.5a7 7 0 0 1 14 0C19 14.8 12 21 12 21z" />
    <circle cx="12" cy="9.5" r="2.5" />
  </Icon>
);

export const LayersIcon = ({ size = 19, stroke = "#f2f5fa" }: Props) => (
  <Icon size={size} stroke={stroke}>
    <path d="M12 3l9 5-9 5-9-5z" />
    <path d="M3 13l9 5 9-5" />
  </Icon>
);

export const NorthIcon = ({ size = 19, stroke = "#f2f5fa" }: Props) => (
  <Icon size={size} stroke={stroke}>
    <path d="M12 3l5 16-5-4-5 4z" />
  </Icon>
);

export const PlusIcon = ({ size = 19, stroke = "#f2f5fa" }: Props) => (
  <Icon size={size} stroke={stroke}>
    <path d="M12 5v14M5 12h14" />
  </Icon>
);

export const MinusIcon = ({ size = 19, stroke = "#f2f5fa" }: Props) => (
  <Icon size={size} stroke={stroke}>
    <path d="M5 12h14" />
  </Icon>
);

export const CloseIcon = ({ size = 18, stroke = "#f2f5fa" }: Props) => (
  <Icon size={size} stroke={stroke}>
    <path d="M6 6l12 12M18 6L6 18" />
  </Icon>
);

export const RouteIcon = ({ size = 20, stroke = "#ffffff" }: Props) => (
  <Icon size={size} stroke={stroke}>
    <circle cx="6" cy="18" r="2" />
    <circle cx="18" cy="6" r="2" />
    <path d="M8 18h7a3 3 0 0 0 0-6H9a3 3 0 0 1 0-6h7" />
  </Icon>
);

export const PhotoIcon = ({ size = 20, stroke = "#f2f5fa" }: Props) => (
  <Icon size={size} stroke={stroke}>
    <rect x="3" y="5" width="18" height="14" rx="1" />
    <path d="M3 16l5-5 4 4 3-3 6 6" />
  </Icon>
);
