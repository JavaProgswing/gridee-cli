# Gridee 1.71 API reference (APK-derived)

Source: static inspection of the installed `com.gridee.parking` APK (`versionName=1.71`, `versionCode=72`) on 2026-08-20. Embedded primary base URL: `https://gridee.onrender.com/`.

This reference describes the Retrofit interface compiled into the client. It does **not** prove that a route is currently enabled, that the server accepts every client-declared field, or that the current account has the required role. `JsonElement` means the client deliberately accepts an untyped JSON shape, so an exact response schema cannot be recovered from the interface alone. Authentication is normally handled by the app's interceptor; the examples below intentionally omit tokens and executable replay instructions.

## Authentication and account

| Method and route | App usage | Request | Declared response |
|---|---|---|---|
| `POST api/auth/login` | Email/password sign-in. | JSON `AuthRequest` | `AuthResponse` |
| `POST api/auth/register` | Create a user profile/account. | JSON `UserRegistration` | `AuthResponse` |
| `POST api/auth/google` | Exchange Google sign-in credentials. | JSON `Map<String,String>`; exact keys are not fixed by the interface. | `AuthResponse` |
| `POST api/auth/firebase/exchange` | Exchange a Firebase ID token for an app session. | JSON `FirebaseTokenExchangeRequest` | `AuthResponse` |
| `GET api/oauth2/user` | Read the current OAuth2 principal/profile. | None. | `Map<String,Object>` |
| `GET api/users/{id}` | Load a user profile by `id`. | Path: `id`. | `User` |
| `PUT api/users/{id}` | Update profile, vehicle, parking-lot, or credential fields. | Path: `id`; JSON `UpdateUserRequest`. | Empty body (`Void`). |

Request bodies:

```text
AuthRequest { email: string, password: string }
FirebaseTokenExchangeRequest { idToken: string }
UserRegistration {
  email: string, name: string, parkingLotName: string,
  password: string, phone: string, vehicleNumbers: string[]
}
UpdateUserRequest {
  email: string, name: string, parkingLotId: string, parkingLotName: string,
  password: string, phone: string, vehicleNumbers: string[]
}
```

`AuthResponse`:

```text
{
  token: string, tokenType: string, message: string,
  isNewUser: boolean, mfaEnabled: boolean, mfaRequired: boolean,
  profileComplete: boolean, requiresProfileCompletion: boolean,
  user: UserResponseDto
}
```

`UserResponseDto` fields: `id`, `name`, `email`, `phone`, `role`, `active`, `firstUser`, `parkingLotId`, `parkingLotName`, `vehicleNumbers[]`, `walletCoins`, `createdAt`, `updatedAt`.

`User` fields: `id`, `name`, `email`, `phone`, `role`, `firstUser`, `parkingLotId`, `parkingLotName`, `vehicleNumbers[]`, `defaultVehicle`, `walletCoins`.

## Configuration

| Method and route | App usage | Request | Declared response |
|---|---|---|---|
| `GET api/config/all` | Fetch remote feature flags, booking limits, financial settings, app-version gates, and platform settings. | None. | `AppConfigResponse` |

`AppConfigResponse` is `{ data: AppRemoteConfig, message, success, status, error, timestamp }`. `AppRemoteConfig` contains `id`, `description`, `schemaVersion`, `features`, `booking`, `financial`, `home`, `notification`, `platform`, `versions`, `customSettings`, `createdAt`, `lastUpdatedAt`, `updatedBy`, and `cacheTtlSeconds`.

Notable nested fields observed in the APK include booking duration/concurrency rules, feature flags such as `bookingFeatureEnabled` and `walletFeatureEnabled`, financial limits such as `minWalletTopUpAmount`/`maxWalletTopUpAmount`, and app-version/update gates. They are server configuration, not client authority to bypass validation.

## Parking lots and parking spots

Several identical routes have both typed and `JsonElement` client methods. This lets the app tolerate older or wrapped server payloads.

| Method and route | App usage | Request | Declared response |
|---|---|---|---|
| `GET api/parking-lots` | List parking lots. | None. | `List<ParkingLot>`; alternate method: `JsonElement`. |
| `GET api/parking-lots?organizationType={value}` | Filter lots by organization type. | Query: `organizationType: string`. | `List<ParkingLot>` |
| `GET api/parking-lots/list/by-names` | Populate lot-name selectors. | None. | `List<string>` |
| `GET api/parking-lots/search/by-name?name={value}` | Resolve one lot from its name. | Query: `name: string`. | `ParkingLot` |
| `GET api/parking-lots/{lotId}/booking-policy` | Load access, payment, booking-window, and validation rules for a lot. | Path: `lotId`. | `ParkingLotBookingPolicy` |
| `GET api/parking-lots/{lotId}/spots` | List spots for one lot. | Path: `lotId`. | `List<ParkingSpot>`; alternate method: `JsonElement`. |
| `GET api/parking-spots` | List spots across the visible scope. | None. | `List<ParkingSpot>`; alternate method: `JsonElement`. |
| `GET api/parking-spots/lot/{lotId}` | Legacy/alternate list of spots by lot. | Path: `lotId`. | `List<ParkingSpot>`; alternate method: `JsonElement`. |
| `GET api/parking-spots/id/{id}` | Fetch one spot. | Path: `id`. | `ParkingSpot` |
| `GET api/parking-spots/available` | Find availability for a time interval. | Queries: `lotId`, `startTime`, `endTime` (strings). | `List<SpotAvailabilityInfo>` |
| `GET api/parking-lots/{lotId}/spots/available` | Find availability within a lot/time interval. | Path: `lotId`; queries: `startTime`, `endTime`. | `List<SpotAvailabilityInfo>` |
| `GET api/parking-lots/{lotId}/spots/{spotId}/available` | Boolean availability check for one spot/time interval. | Paths: `lotId`, `spotId`; queries: `startTime`, `endTime`. | `boolean` |

`ParkingLot` fields:

```text
id, name, address, location, latitude, longitude, active,
availableSpots, totalSpots, lotType, paymentModel,
organizationId, organizationName, organizationType,
locationId, locationName, bookingPolicy
```

`ParkingSpot` fields:

```text
id, lotId, lotName, name, spotCode, zoneName,
slotId, slotName, capacity, available, status, bookingRate
```

`SpotAvailabilityInfo` is `{ spot: ParkingSpot, available: boolean, availableCapacity: int, bookedCount: int }`.

`ParkingLotBookingPolicy` fields:

```text
accessTypes[], advanceBookingDays, allowAdvanceBooking, allowOvernightBookings,
allowWalkIn, bookingMode, bookingRequired, dailyBookingEndTime,
fixedTimeSlotsEnabled, nextDayBookingOpenTime, paymentModel, paymentRequired,
penaltyEnabled, pricingType, refundPolicy, requiresResidentApproval,
requiresUserVerification, requiresVehicleRegistration, supportsANPR,
supportsOperatorValidation, supportsQRCode, validationMode, welcomeBonusAmount
```

The interface stores `startTime`, `endTime`, `checkInTime`, and `checkOutTime` as strings. The exact accepted wire format is not declared by Retrofit; the app supplies its configured date formatter.

## Bookings

| Method and route | App usage | Request | Declared response |
|---|---|---|---|
| `POST api/bookings/{userId}/create` | Create a booking using the global/legacy route. | Path: `userId`; JSON `CreateBookingRequest`. | `Booking` |
| `POST api/parking-lots/{lotId}/bookings/{userId}/create` | Create a booking scoped to a lot. | Paths: `lotId`, `userId`; JSON `CreateBookingRequest`. | `Booking` |
| `GET api/bookings/{userId}/{bookingId}` | Fetch one booking. | Paths: `userId`, `bookingId`. | `Booking` |
| `GET api/parking-lots/{lotId}/bookings/{userId}/{bookingId}` | Fetch one lot-scoped booking. | Paths: `lotId`, `userId`, `bookingId`. | `Booking` |
| `GET api/bookings/{userId}/all` | Fetch current/all user bookings; app parser accepts multiple envelope shapes. | Path: `userId`. | `JsonElement` |
| `GET api/parking-lots/{lotId}/bookings/{userId}/all` | Fetch current/all user bookings for a lot. | Paths: `lotId`, `userId`. | `JsonElement` |
| `GET api/bookings/{userId}/all/history` | Fetch booking history. | Path: `userId`. | `JsonElement` |
| `GET api/parking-lots/{lotId}/bookings/{userId}/history` | Fetch lot-scoped booking history. | Paths: `lotId`, `userId`. | `JsonElement` |
| `POST api/bookings/{userId}/{bookingId}/cancel` | Cancel a booking. | Paths: `userId`, `bookingId`; no body. | Empty body (`Void`). |
| `PUT api/bookings/{userId}/{bookingId}/extend` | Extend/change checkout details. | Paths: `userId`, `bookingId`; JSON `Map<string,string>`. Exact accepted keys are not declared by the interface. | `Booking` |
| `GET api/bookings/{userId}/{bookingId}/priceBreakup` | Retrieve calculated price components. | Paths: `userId`, `bookingId`. | `Map<string,object>` |
| `GET api/bookings/{userId}/{bookingId}/penalty` | Retrieve the current penalty amount. | Paths: `userId`, `bookingId`. | `double` |
| `POST api/bookings/{userId}/checkin/{bookingId}` | User check-in by QR, PIN, or vehicle data. | Paths: `userId`, `bookingId`; JSON `CheckInRequest`. | `Booking` |
| `POST api/bookings/{userId}/checkout/{bookingId}` | User checkout. | Paths: `userId`, `bookingId`; JSON `CheckInRequest`. | `Booking` |

`CreateBookingRequest`:

```text
{
  spotId: string,
  lotId: string,
  checkInTime: string,
  checkOutTime: string,
  vehicleNumber: string
}
```

`CheckInRequest`:

```text
{
  mode: "QR_CODE" | "PIN" | "VEHICLE_NUMBER",
  parkingLotId: string,
  parkingSpotId: string,
  pin: string,
  qrCode: string,
  vehicleNumber: string
}
```

Fields may be conditionally optional depending on `mode`; the Retrofit interface does not encode that server-side rule.

`Booking` fields:

```text
id, userId, spotId, lotId, lotName, vehicleNumber, status, bookingType,
checkInTime, checkOutTime, actualCheckInTime, actualCheckOutTime,
createdAt, updatedAt, cancelledAt, archivedAt, amount, paymentModel,
qrCode, qrCodeScanned, checkInOperatorId, checkOutOperatorId,
autoCompleted, balanceSettled, endingReminderSent, endingReminderSentAt,
organizationId, organizationName, organizationType, locationId, locationName
```

## Wallet and payments

The dedicated wallet-topup command invokes the authenticated, server-controlled initiation route and requires --execute to send. It does not extract tokens, directly credit a wallet, or bypass payment and server-side validation.

| Method and route | App usage | Request | Declared response |
|---|---|---|---|
| `GET api/users/{userId}/wallet` | Display wallet balance and recent transactions. | Path: `userId`. | `WalletDetails` |
| `GET api/users/{userId}/wallet/transactions` | Paginated transaction history. | Path: `userId`; optional queries: `page: int`, `size: int`, repeated `sort: string`. | `WalletTransactionsResponse` |
| `POST api/users/{userId}/wallet/topup` | App-controlled wallet top-up initiation. | Path: `userId`; JSON model `TopUpRequest` containing an `amount` number. | `TopUpResponse` |
| `POST api/payments/initiate` | Create a payment-gateway session. | JSON `PaymentInitiateRequest`. | `PaymentInitiateResponse` |
| `GET api/payments/status/{orderId}` | Poll payment/order completion and wallet-credit status. | Path: `orderId`. | `PaymentStatusResponse` |

`PaymentInitiateRequest` fields: `userId`, `amount`, `parkingLotId`, `organizationId`, `locationId`.

Response models:

```text
WalletDetails { balance: number, transactions: WalletTransaction[] }

WalletTransactionsResponse {
  content: WalletTransaction[], number: int, totalElements: long,
  totalPages: int, last: boolean
}

WalletTransaction {
  id, type, amount, balanceAfter, currency, status, method, gateway,
  referenceId, bookingId, lotId, lotName, spotId, description,
  failureReason, timestamp
}

TopUpResponse { orderId, amount, balance, currency }
PaymentInitiateResponse { orderId, paymentSessionId, gateway, environment }
PaymentStatusResponse {
  orderId, status, message, amount, currency, gateway, gatewayPaymentId,
  walletCredited, parkingLotId, parkingLotName, organizationId,
  organizationName, locationId, locationName
}
```

The presence of `walletCredited` in `PaymentStatusResponse` indicates that credit confirmation is expected to be tied to payment status. Static client code alone cannot establish the complete server-side validation path.

## Custom advertising

| Method and route | App usage | Request | Declared response |
|---|---|---|---|
| `GET api/custom-ads/active` | Fetch active campaigns for a placement/platform and optional lot. | Queries: `placement: string`, `platform: string`, optional `parkingLotId: string`. | `JsonElement` |
| `POST api/custom-ads/{adId}/impression` | Report that a custom campaign was shown. | Path: `adId`; no body. | Empty body (`Void`). |
| `POST api/custom-ads/{adId}/click` | Report a custom campaign click/open. | Path: `adId`; no body. | Empty body (`Void`). |

The client parser recognizes ad objects containing `id`, `title`, `subtitle`, `imageUrl`, `clickUrl`, `ctaText`, `placement`, `platform`, `parkingLotId`, `organizationId`, `locationId`, `priority`, `displayFrequency`, `dismissible`, `aspectRatio`, `startAtMillis`, `endAtMillis`, `impressions`, and `clicks`. The endpoint itself is declared as untyped `JsonElement`, so list/envelope structure is not guaranteed by the interface.

No separately named “reward credit” endpoint appears in `ApiService`. Unity/Google rewarded-ad SDK traffic is separate from these three custom-ad routes.

## Notifications

| Method and route | App usage | Request | Declared response |
|---|---|---|---|
| `POST api/notifications/tokens` | Register a push-notification device token. | Explicit `Authorization` header; JSON `DeviceTokenRegisterRequest`. | Empty body (`Void`). |
| `DELETE api/notifications/tokens` | Unregister a push token. | Explicit `Authorization` header; JSON `DeviceTokenUnregisterRequest`. | Empty body (`Void`). |

```text
DeviceTokenRegisterRequest { token, deviceId, platform, appVersion }
DeviceTokenUnregisterRequest { token }
```

## Support tickets

| Method and route | App usage | Request | Declared response |
|---|---|---|---|
| `POST api/support/tickets` | Open a support ticket. | JSON `CreateSupportTicketRequest`. | `SupportTicket` |
| `GET api/support/tickets/my` | List the signed-in user's tickets. | None. | `List<SupportTicket>` |
| `GET api/support/tickets/{ticketId}` | Fetch a ticket/conversation. | Path: `ticketId`. | `SupportTicket` |
| `POST api/support/tickets/{ticketId}/messages` | Add a conversation message. | Path: `ticketId`; JSON `AddSupportTicketMessageRequest`. | `SupportTicket` |

```text
CreateSupportTicketRequest {
  subject, description, priority, parkingLotId, parkingLotName
}
AddSupportTicketMessageRequest { message }

SupportTicket {
  id, userId, userName, userEmail, subject, description, priority, status,
  parkingLotId, parkingLotName, messages: SupportTicketMessage[],
  createdAt, updatedAt, resolvedAt, resolvedBy
}
SupportTicketMessage { messageId, message, senderId, senderRole, sentAt }
```

## Operator and admin surface

These methods are declared by the same APK but require operator/admin authorization. The normal user automation does not invoke them.

| Method and route | App usage | Request | Declared response |
|---|---|---|---|
| `GET api/operator/parking-spots` | Operator spot inventory. | None. | `List<ParkingSpot>`; alternate method: `JsonElement`. |
| `GET api/operator/parking-lots/{lotId}/spots` | Operator inventory for one lot. | Path: `lotId`. | `JsonElement` |
| `POST api/operator/bookings/checkin` | Operator check-in. | JSON `CheckInRequest`. | `Booking` |
| `POST api/operator/parking-lots/{parkingLotId}/bookings/checkin` | Lot-scoped operator check-in. | Path: `parkingLotId`; JSON `CheckInRequest`. | `Booking` |
| `POST api/operator/bookings/checkout` | Operator checkout. | JSON `CheckInRequest`. | `Booking` |
| `POST api/operator/parking-lots/{parkingLotId}/bookings/checkout` | Lot-scoped operator checkout. | Path: `parkingLotId`; JSON `CheckInRequest`. | `Booking` |
| `PUT api/admin/bookings/{userId}/{bookingId}` | Administrative booking-status update. | Paths: `userId`, `bookingId`; JSON `Map<string,string>`. Exact accepted keys are not declared. | `Booking` |

## Confidence and limitations

- Method, route, Retrofit path/query/header/body annotations, and declared return types: **high confidence**, extracted directly from `ApiService`.
- Model field names: **high confidence**, extracted from Kotlin metadata and Gson `SerializedName` annotations where present.
- Field required/nullable rules: **medium confidence**; Kotlin constructors expose some nullability, but server validation may differ.
- `JsonElement` response envelopes, error bodies, HTTP status codes, and server-only validation: **unknown from the client interface**.
- No live write endpoint was called while producing this document.

