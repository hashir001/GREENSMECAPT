import { Leaf } from 'lucide-react'
import { Link } from 'react-router-dom'

export function Brand() {
  return (
    <Link className="brand" to="/" aria-label="Go to GREENSMECAPT home">
      <span className="brand__mark" aria-hidden="true">
        <Leaf size={20} strokeWidth={2.2} />
      </span>
      <span className="brand__name">
        GREENSME<span>CAPT</span>
      </span>
    </Link>
  )
}
