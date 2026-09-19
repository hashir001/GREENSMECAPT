import { Leaf } from 'lucide-react'

export function Brand() {
  return (
    <div className="brand">
      <span className="brand__mark" aria-hidden="true">
        <Leaf size={20} strokeWidth={2.2} />
      </span>
      <span className="brand__name">
        GREENSME<span>CAPT</span>
      </span>
    </div>
  )
}
