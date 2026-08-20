# Gridee 1.71 endpoint inventory

Source: static inspection of the installed APK (`versionName=1.71`, `versionCode=72`) on 2026-08-20. Primary base URL: `https://gridee.onrender.com/`. This inventory does not prove that every legacy/operator endpoint is enabled for the current account.

## Booking and parking

| Method | Path | Purpose |
|---|---|---|
| GET | `api/parking-lots` | list lots; also used with organization filters/payload variants |
| GET | `api/parking-lots/list/by-names` | list lot names |
| GET | `api/parking-lots/search/by-name` | find lot by name |
| GET | `api/parking-lots/{lotId}/booking-policy` | lot-specific booking policy |
| GET | `api/parking-lots/{lotId}/spots` | list lot spots |
| GET | `api/parking-lots/{lotId}/spots/available` | available spots for a lot |
| GET | `api/parking-lots/{lotId}/spots/{spotId}/available` | check a spot/time range |
| GET | `api/parking-spots` | list spots |
| GET | `api/parking-spots/available` | global availability query |
| GET | `api/parking-spots/id/{id}` | get spot by ID |
| GET | `api/parking-spots/lot/{lotId}` | list spots by lot |
| POST | `api/parking-lots/{lotId}/bookings/{userId}/create` | create a lot-scoped booking |
| GET | `api/parking-lots/{lotId}/bookings/{userId}/all` | current lot bookings |
| GET | `api/parking-lots/{lotId}/bookings/{userId}/history` | lot booking history |
| GET | `api/parking-lots/{lotId}/bookings/{userId}/{bookingId}` | lot booking details |
| POST | `api/bookings/{userId}/create` | legacy/global booking creation |
| GET | `api/bookings/{userId}/all` | current bookings |
| GET | `api/bookings/{userId}/all/history` | booking history |
| GET | `api/bookings/{userId}/{bookingId}` | booking details |
| POST | `api/bookings/{userId}/{bookingId}/cancel` | cancel booking |
| PUT | `api/bookings/{userId}/{bookingId}/extend` | extend booking |
| GET | `api/bookings/{userId}/{bookingId}/priceBreakup` | price breakdown |
| GET | `api/bookings/{userId}/{bookingId}/penalty` | penalty information |
| POST | `api/bookings/{userId}/checkin/{bookingId}` | check in |
| POST | `api/bookings/{userId}/checkout/{bookingId}` | check out |

The booking request model contains `spotId`, `lotId`, `checkInTime`, `checkOutTime`, and `vehicleNumber`. The automation intentionally lets the installed app construct and authenticate this request.

## Wallet and payments (documented, never invoked by this project)

| Method | Path | Purpose |
|---|---|---|
| GET | `api/users/{userId}/wallet` | wallet details/balance |
| GET | `api/users/{userId}/wallet/transactions` | paginated transaction history |
| POST | `api/users/{userId}/wallet/topup` | app-controlled top-up request |
| POST | `api/payments/initiate` | initiate payment |
| GET | `api/payments/status/{orderId}` | payment status |

The CLI can submit the documented top-up initiation body for an authorized account after explicit --execute confirmation. The normal payment flow and all server-side authorization and validation still apply.

## Account, configuration, notifications, and support

| Method | Path |
|---|---|
| GET | `api/config/all` |
| POST | `api/auth/login` |
| POST | `api/auth/register` |
| POST | `api/auth/google` |
| POST | `api/auth/firebase/exchange` |
| GET | `api/oauth2/user` |
| GET / PUT | `api/users/{id}` |
| POST / DELETE | `api/notifications/tokens` |
| POST / GET | `api/support/tickets` / `api/support/tickets/my` |
| GET | `api/support/tickets/{ticketId}` |
| POST | `api/support/tickets/{ticketId}/messages` |
| GET | `api/custom-ads/active` |
| POST | `api/custom-ads/{adId}/impression` |
| POST | `api/custom-ads/{adId}/click` |

## Operator/admin surface

The APK also declares operator check-in/check-out and administrative booking-status endpoints. They require roles the normal user automation does not have and are intentionally omitted from executable code.

