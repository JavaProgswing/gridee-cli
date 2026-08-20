# Gridee 1.71 complete API route inventory

Source: static inspection of the installed `com.gridee.parking` APK (`versionName=1.71`, `versionCode=72`) on 2026-08-20. The primary base URL embedded in this build is `https://gridee.onrender.com/`.

This is a declaration inventory, not proof that every route is enabled for the current account. Duplicate paths below indicate distinct client methods/query variants. No authentication tokens, private request bodies, replay commands, or write-endpoint invocations are included.

## Authentication and user

| Method | Route |
|---|---|
| POST | `api/auth/login` |
| POST | `api/auth/register` |
| POST | `api/auth/google` |
| POST | `api/auth/firebase/exchange` |
| GET | `api/oauth2/user` |
| GET | `api/users/{id}` |
| PUT | `api/users/{id}` |

## Parking lots, spots, availability, and policy

| Method | Route | Notes |
|---|---|---|
| GET | `api/parking-lots` | Declared by three client methods/query variants. |
| GET | `api/parking-lots/list/by-names` | Lot names/list lookup. |
| GET | `api/parking-lots/search/by-name` | Name search. |
| GET | `api/parking-lots/{lotId}/booking-policy` | Lot-specific policy. |
| GET | `api/parking-lots/{lotId}/spots` | Declared by two client methods/query variants. |
| GET | `api/parking-lots/{lotId}/spots/available` | Lot availability. |
| GET | `api/parking-lots/{lotId}/spots/{spotId}/available` | Spot/time availability. |
| GET | `api/parking-spots` | Declared by two client methods/query variants. |
| GET | `api/parking-spots/available` | Global availability query. |
| GET | `api/parking-spots/id/{id}` | Spot by ID. |
| GET | `api/parking-spots/lot/{lotId}` | Declared by two client methods/query variants. |

## Bookings

| Method | Route |
|---|---|
| POST | `api/bookings/{userId}/create` |
| POST | `api/parking-lots/{lotId}/bookings/{userId}/create` |
| GET | `api/bookings/{userId}/{bookingId}` |
| GET | `api/parking-lots/{lotId}/bookings/{userId}/{bookingId}` |
| GET | `api/bookings/{userId}/all` |
| GET | `api/parking-lots/{lotId}/bookings/{userId}/all` |
| GET | `api/bookings/{userId}/all/history` |
| GET | `api/parking-lots/{lotId}/bookings/{userId}/history` |
| POST | `api/bookings/{userId}/{bookingId}/cancel` |
| PUT | `api/bookings/{userId}/{bookingId}/extend` |
| GET | `api/bookings/{userId}/{bookingId}/priceBreakup` |
| GET | `api/bookings/{userId}/{bookingId}/penalty` |
| POST | `api/bookings/{userId}/checkin/{bookingId}` |
| POST | `api/bookings/{userId}/checkout/{bookingId}` |

The observed booking request model contains `spotId`, `lotId`, `checkInTime`, `checkOutTime`, and `vehicleNumber`. The project lets the installed app construct, authenticate, and validate this request.

## Wallet and payments

| Method | Route | Observed purpose |
|---|---|---|
| GET | `api/users/{userId}/wallet` | Wallet details/balance. |
| GET | `api/users/{userId}/wallet/transactions` | Transaction history. |
| POST | `api/users/{userId}/wallet/topup` | App-controlled top-up request. |
| POST | `api/payments/initiate` | Initiate payment. |
| GET | `api/payments/status/{orderId}` | Payment status. |

The CLI provides a preview-by-default wrapper for the normal authenticated top-up initiation request. The server remains authoritative: this is not a direct-credit option and it does not bypass payment, amount limits, authorization, or other validation.

## Advertising

| Method | Route |
|---|---|
| GET | `api/custom-ads/active` |
| POST | `api/custom-ads/{adId}/impression` |
| POST | `api/custom-ads/{adId}/click` |

The APK route interface exposes impression/click callbacks but no separately named wallet-credit endpoint. Any reward application may occur server-side as part of one of these flows or in a route not declared by this client interface. Confirming that would require authorized server-side logs or a controlled security assessment; this project does not replay or manipulate the flow.

## Notifications, configuration, and support

| Method | Route |
|---|---|
| GET | `api/config/all` |
| POST | `api/notifications/tokens` |
| DELETE | `api/notifications/tokens` |
| POST | `api/support/tickets` |
| GET | `api/support/tickets/my` |
| GET | `api/support/tickets/{ticketId}` |
| POST | `api/support/tickets/{ticketId}/messages` |

## Operator and admin routes

| Method | Route |
|---|---|
| GET | `api/operator/parking-spots` |
| GET | `api/operator/parking-lots/{lotId}/spots` |
| POST | `api/operator/bookings/checkin` |
| POST | `api/operator/parking-lots/{parkingLotId}/bookings/checkin` |
| POST | `api/operator/bookings/checkout` |
| POST | `api/operator/parking-lots/{parkingLotId}/bookings/checkout` |
| PUT | `api/admin/bookings/{userId}/{bookingId}` |

These routes are role-gated surfaces and are not used by the user-side automation.

