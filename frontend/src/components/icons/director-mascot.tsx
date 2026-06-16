import type { SVGProps } from 'react'

/**
 * Mascot Đạo diễn AI — chú "folder" cam dễ thương: thân tam giác bo tròn màu cam,
 * mặt cười trên tấm vàng phía trước, hai bàn chân vàng thò ra dưới đáy.
 * Đa màu (không dùng currentColor) để giữ đúng nhận diện nhân vật.
 */
export function DirectorMascot(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 64 64" fill="none" aria-hidden {...props}>
      {/* Hai bàn chân vàng — vẽ trước để thân cam đè lên, chỉ ló phần dưới */}
      <rect x="21" y="47" width="9" height="13" rx="4.5" fill="#F4B81E" />
      <rect x="34" y="47" width="9" height="13" rx="4.5" fill="#F4B81E" />
      {/* Thân cam: tam giác hướng lên, các góc bo tròn */}
      <path
        d="M32 5c3.4 0 6.3 2.1 7.6 5.2l13.1 35.4c1.6 4.3-1.5 8.9-6.1 8.9H17.4c-4.6 0-7.7-4.6-6.1-8.9L24.4 10.2C25.7 7.1 28.6 5 32 5Z"
        fill="#F26A26"
      />
      {/* Tấm vàng mặt trước */}
      <rect x="19" y="28" width="26" height="23" rx="7" fill="#FBC53D" />
      {/* Mắt */}
      <circle cx="27" cy="37" r="2" fill="#2A2118" />
      <circle cx="37" cy="37" r="2" fill="#2A2118" />
      {/* Miệng cười */}
      <path
        d="M26.5 42.5c1.6 2.4 3.4 3.5 5.5 3.5s3.9-1.1 5.5-3.5"
        stroke="#2A2118"
        strokeWidth="2.2"
        strokeLinecap="round"
      />
    </svg>
  )
}
