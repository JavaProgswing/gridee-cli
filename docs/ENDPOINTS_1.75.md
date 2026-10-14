# Gridee APK endpoint audit

- APK: `C:\Users\yashasvi\Downloads\gridee_cli\analysis\gridee-1.75-device\base.apk`
- Application ID: `com.gridee.parking`
- Version: `1.75` (code `83`)
- Unique Retrofit endpoints: **43**
- Retrofit declarations: **43**
- Request/response models extracted: **30**


Patterns below are inferred from Retrofit annotations and APK model fields.
They describe JSON structure, not server-side authorization or value constraints.

| Method | Route | Request pattern | Response pattern | Query |
|---|---|---|---|---|
| POST | `/api/auth/firebase/exchange` | `FirebaseTokenExchangeRequest` | `AuthResponse` | - |
| POST | `/api/auth/google` | `Map<String, String>` | `AuthResponse` | - |
| POST | `/api/auth/login` | `AuthRequest` | `AuthResponse` | - |
| GET | `/api/bookings/{userId}/all` | `none` | `JsonElement` | - |
| GET | `/api/bookings/{userId}/all/history` | `none` | `JsonElement` | - |
| POST | `/api/bookings/{userId}/create` | `CreateBookingRequest` | `Booking` | - |
| GET | `/api/bookings/{userId}/history/page` | `none` | `JsonElement` | status, page, size |
| GET | `/api/bookings/{userId}/{bookingId}` | `none` | `Booking` | - |
| POST | `/api/bookings/{userId}/{bookingId}/cancel` | `none` | `null` | - |
| GET | `/api/config/all` | `none` | `AppConfigResponse` | - |
| GET | `/api/custom-ads/active` | `none` | `JsonElement` | placement, platform, parkingLotId |
| POST | `/api/custom-ads/{adId}/click` | `none` | `null` | - |
| POST | `/api/custom-ads/{adId}/impression` | `none` | `null` | - |
| DELETE | `/api/notifications/tokens` | `DeviceTokenUnregisterRequest` | `null` | - |
| POST | `/api/notifications/tokens` | `DeviceTokenRegisterRequest` | `null` | - |
| POST | `/api/operator/bookings/checkin` | `CheckInRequest` | `Booking` | - |
| POST | `/api/operator/bookings/checkout` | `CheckInRequest` | `Booking` | - |
| GET | `/api/operator/parking-lots/{lotId}/spots` | `none` | `JsonElement` | - |
| POST | `/api/operator/parking-lots/{parkingLotId}/bookings/checkin` | `CheckInRequest` | `Booking` | - |
| POST | `/api/operator/parking-lots/{parkingLotId}/bookings/checkout` | `CheckInRequest` | `Booking` | - |
| GET | `/api/operator/parking-spots` | `none` | `JsonElement` | - |
| GET | `/api/parking-lots` | `none` | `List<ParkingLot> / JsonElement` | organizationType, organizationId, locationId |
| GET | `/api/parking-lots/{lotId}/booking-policy` | `none` | `ParkingLotBookingPolicy` | - |
| GET | `/api/parking-lots/{lotId}/bookings/{userId}/all` | `none` | `JsonElement` | - |
| POST | `/api/parking-lots/{lotId}/bookings/{userId}/create` | `CreateBookingRequest` | `Booking` | - |
| GET | `/api/parking-lots/{lotId}/bookings/{userId}/history` | `none` | `JsonElement` | - |
| GET | `/api/parking-lots/{lotId}/bookings/{userId}/history/page` | `none` | `JsonElement` | status, page, size |
| GET | `/api/parking-lots/{lotId}/spots` | `none` | `List<ParkingSpot> / JsonElement` | - |
| GET | `/api/parking-spots/id/{id}` | `none` | `ParkingSpot` | - |
| GET | `/api/parking-spots/lot/{lotId}` | `none` | `List<ParkingSpot> / JsonElement` | - |
| POST | `/api/payments/initiate` | `PaymentInitiateRequest` | `PaymentInitiateResponse` | - |
| GET | `/api/payments/status/{orderId}` | `none` | `PaymentStatusResponse` | - |
| POST | `/api/support/tickets` | `CreateSupportTicketRequest` | `SupportTicket` | - |
| GET | `/api/support/tickets/my` | `none` | `List<SupportTicket>` | - |
| GET | `/api/support/tickets/{ticketId}` | `none` | `SupportTicket` | - |
| POST | `/api/support/tickets/{ticketId}/messages` | `AddSupportTicketMessageRequest` | `SupportTicket` | - |
| GET | `/api/users/{id}` | `none` | `User` | - |
| PUT | `/api/users/{id}` | `UpdateUserRequest` | `null` | - |
| GET | `/api/users/{userId}/wallet` | `none` | `WalletDetails` | - |
| POST | `/api/users/{userId}/wallet/topup` | `TopUpRequest` | `TopUpResponse` | - |
| GET | `/api/users/{userId}/wallet/transactions` | `none` | `WalletTransactionsResponse` | page, size, sort |
| GET | `/api/v1/locations` | `none` | `List<ParkingLocation>` | organizationId |
| GET | `/api/v1/organizations` | `none` | `List<ParkingOrganization>` | - |

## APK model field patterns

### AddSupportTicketMessageRequest

APK class: `com.gridee.parking.data.model.AddSupportTicketMessageRequest`

```json
{
  "message": "<string>"
}
```

### AppConfigResponse

APK class: `com.gridee.parking.data.model.AppConfigResponse`

```json
{}
```

### AuthRequest

APK class: `com.gridee.parking.data.model.AuthRequest`

```json
{
  "email": "<string>",
  "password": "<string>"
}
```

### AuthResponse

APK class: `com.gridee.parking.data.model.AuthResponse`

```json
{
  "isNewUser": "<boolean>",
  "message": "<string>",
  "mfaEnabled": "<boolean>",
  "mfaRequired": "<boolean>",
  "profileComplete": "<boolean>",
  "requiresProfileCompletion": "<boolean>",
  "token": "<string>",
  "tokenType": "<string>",
  "user": "<UserResponseDto>"
}
```

### Booking

APK class: `com.gridee.parking.data.model.Booking`

```json
{
  "actualCheckInTime": "<Date>",
  "actualCheckOutTime": "<Date>",
  "amount": "<number>",
  "archivedAt": "<Date>",
  "autoCompleted": "<boolean>",
  "balanceSettled": "<boolean>",
  "bookingType": "<string>",
  "cancelledAt": "<Date>",
  "checkInOperatorId": "<string>",
  "checkInTime": "<Date>",
  "checkOutOperatorId": "<string>",
  "checkOutTime": "<Date>",
  "createdAt": "<Date>",
  "endingReminderSent": "<boolean>",
  "endingReminderSentAt": "<Date>",
  "id": "<string>",
  "locationId": "<string>",
  "locationName": "<string>",
  "lotId": "<string>",
  "lotName": "<string>",
  "organizationId": "<string>",
  "organizationName": "<string>",
  "organizationType": "<string>",
  "paymentModel": "<string>",
  "qrCode": "<string>",
  "qrCodeScanned": "<boolean>",
  "spotId": "<string>",
  "spotName": "<string>",
  "status": "<string>",
  "updatedAt": "<Date>",
  "userId": "<string>",
  "vehicleNumber": "<string>"
}
```

### CheckInMode

APK class: `com.gridee.parking.data.model.CheckInMode`

```json
{}
```

### CheckInRequest

APK class: `com.gridee.parking.data.model.CheckInRequest`

```json
{
  "mode": "<CheckInMode>",
  "parkingLotId": "<string>",
  "parkingSpotId": "<string>",
  "pin": "<string>",
  "qrCode": "<string>",
  "vehicleNumber": "<string>"
}
```

### CreateBookingRequest

APK class: `com.gridee.parking.data.model.CreateBookingRequest`

```json
{
  "checkInTime": "<string>",
  "checkOutTime": "<string>",
  "lotId": "<string>",
  "spotId": "<string>",
  "vehicleNumber": "<string>"
}
```

### CreateSupportTicketRequest

APK class: `com.gridee.parking.data.model.CreateSupportTicketRequest`

```json
{
  "description": "<string>",
  "parkingLotId": "<string>",
  "parkingLotName": "<string>",
  "priority": "<string>",
  "subject": "<string>"
}
```

### DeviceTokenRegisterRequest

APK class: `com.gridee.parking.data.model.DeviceTokenRegisterRequest`

```json
{
  "appVersion": "<string>",
  "deviceId": "<string>",
  "platform": "<string>",
  "token": "<string>"
}
```

### DeviceTokenUnregisterRequest

APK class: `com.gridee.parking.data.model.DeviceTokenUnregisterRequest`

```json
{
  "token": "<string>"
}
```

### FirebaseTokenExchangeRequest

APK class: `com.gridee.parking.data.model.FirebaseTokenExchangeRequest`

```json
{
  "idToken": "<string>"
}
```

### ParkingLocation

APK class: `com.gridee.parking.data.model.ParkingLocation`

```json
{
  "active": "<boolean>",
  "address": "<string>",
  "id": "<string>",
  "name": "<string>",
  "organizationId": "<string>"
}
```

### ParkingLot

APK class: `com.gridee.parking.data.model.ParkingLot`

```json
{
  "active": "<boolean>",
  "address": "<string>",
  "availableSpots": "<integer>",
  "bookingPolicy": "<ParkingLotBookingPolicy>",
  "id": "<string>",
  "latitude": "<number>",
  "location": "<string>",
  "locationId": "<string>",
  "locationName": "<string>",
  "longitude": "<number>",
  "lotType": "<string>",
  "name": "<string>",
  "organizationId": "<string>",
  "organizationName": "<string>",
  "organizationType": "<string>",
  "paymentModel": "<string>",
  "totalSpots": "<integer>"
}
```

### ParkingLotBookingPolicy

APK class: `com.gridee.parking.data.model.ParkingLotBookingPolicy`

```json
{
  "accessTypes": "<List<string>>",
  "advanceBookingDays": "<integer>",
  "allowAdvanceBooking": "<boolean>",
  "allowOvernightBookings": "<boolean>",
  "allowWalkIn": "<boolean>",
  "bookingMode": "<string>",
  "bookingRequired": "<boolean>",
  "dailyBookingEndTime": "<string>",
  "fixedTimeSlotsEnabled": "<boolean>",
  "nextDayBookingOpenTime": "<string>",
  "paymentModel": "<string>",
  "paymentRequired": "<boolean>",
  "penaltyEnabled": "<boolean>",
  "pricingType": "<string>",
  "refundPolicy": "<string>",
  "requiresResidentApproval": "<boolean>",
  "requiresUserVerification": "<boolean>",
  "requiresVehicleRegistration": "<boolean>",
  "supportsANPR": "<boolean>",
  "supportsOperatorValidation": "<boolean>",
  "supportsQRCode": "<boolean>",
  "validationMode": "<string>",
  "walletPaymentRequired": "<boolean>",
  "welcomeBonusAmount": "<number>"
}
```

### ParkingOrganization

APK class: `com.gridee.parking.data.model.ParkingOrganization`

```json
{
  "active": "<boolean>",
  "description": "<string>",
  "id": "<string>",
  "name": "<string>",
  "type": "<string>"
}
```

### ParkingSpot

APK class: `com.gridee.parking.data.model.ParkingSpot`

```json
{
  "available": "<integer>",
  "bookingRate": "<number>",
  "capacity": "<integer>",
  "id": "<string>",
  "lotId": "<string>",
  "lotName": "<string>",
  "name": "<string>",
  "slotId": "<integer>",
  "slotName": "<string>",
  "spotCode": "<string>",
  "status": "<string>",
  "zoneName": "<string>"
}
```

### PaymentInitiateRequest

APK class: `com.gridee.parking.data.model.PaymentInitiateRequest`

```json
{
  "amount": "<number>",
  "locationId": "<string>",
  "organizationId": "<string>",
  "parkingLotId": "<string>",
  "userId": "<string>"
}
```

### PaymentInitiateResponse

APK class: `com.gridee.parking.data.model.PaymentInitiateResponse`

```json
{
  "environment": "<string>",
  "gateway": "<string>",
  "orderId": "<string>",
  "paymentSessionId": "<string>"
}
```

### PaymentStatusResponse

APK class: `com.gridee.parking.data.model.PaymentStatusResponse`

```json
{
  "amount": "<number>",
  "currency": "<string>",
  "gateway": "<string>",
  "gatewayPaymentId": "<string>",
  "locationId": "<string>",
  "locationName": "<string>",
  "message": "<string>",
  "orderId": "<string>",
  "organizationId": "<string>",
  "organizationName": "<string>",
  "parkingLotId": "<string>",
  "parkingLotName": "<string>",
  "status": "<string>",
  "walletCredited": "<boolean>"
}
```

### SupportTicket

APK class: `com.gridee.parking.data.model.SupportTicket`

```json
{
  "createdAt": "<Date>",
  "description": "<string>",
  "id": "<string>",
  "messages": "<List<SupportTicketMessage>>",
  "parkingLotId": "<string>",
  "parkingLotName": "<string>",
  "priority": "<string>",
  "resolvedAt": "<Date>",
  "resolvedBy": "<string>",
  "status": "<string>",
  "subject": "<string>",
  "updatedAt": "<Date>",
  "userEmail": "<string>",
  "userId": "<string>",
  "userName": "<string>"
}
```

### SupportTicketMessage

APK class: `com.gridee.parking.data.model.SupportTicketMessage`

```json
{
  "message": "<string>",
  "messageId": "<string>",
  "senderId": "<string>",
  "senderRole": "<string>",
  "sentAt": "<Date>"
}
```

### TopUpRequest

APK class: `com.gridee.parking.data.model.TopUpRequest`

```json
{
  "amount": "<number>"
}
```

### TopUpResponse

APK class: `com.gridee.parking.data.model.TopUpResponse`

```json
{
  "amount": "<number>",
  "balance": "<number>",
  "currency": "<string>",
  "orderId": "<string>"
}
```

### UpdateUserRequest

APK class: `com.gridee.parking.data.model.UpdateUserRequest`

```json
{
  "email": "<string>",
  "name": "<string>",
  "parkingLotId": "<string>",
  "parkingLotName": "<string>",
  "password": "<string>",
  "phone": "<string>",
  "vehicleNumbers": "<List<string>>"
}
```

### User

APK class: `com.gridee.parking.data.model.User`

```json
{
  "defaultVehicle": "<string>",
  "email": "<string>",
  "firstUser": "<boolean>",
  "id": "<string>",
  "name": "<string>",
  "parkingLotId": "<string>",
  "parkingLotName": "<string>",
  "phone": "<string>",
  "role": "<string>",
  "vehicleNumbers": "<List<string>>",
  "walletCoins": "<integer>"
}
```

### UserResponseDto

APK class: `com.gridee.parking.data.model.UserResponseDto`

```json
{
  "active": "<boolean>",
  "createdAt": "<string>",
  "email": "<string>",
  "firstUser": "<boolean>",
  "id": "<string>",
  "name": "<string>",
  "parkingLotId": "<string>",
  "parkingLotName": "<string>",
  "phone": "<string>",
  "role": "<string>",
  "updatedAt": "<string>",
  "vehicleNumbers": "<List<string>>",
  "walletCoins": "<integer>"
}
```

### WalletDetails

APK class: `com.gridee.parking.data.model.WalletDetails`

```json
{
  "balance": "<number>",
  "transactions": "<List<WalletTransaction>>"
}
```

### WalletTransaction

APK class: `com.gridee.parking.data.model.WalletTransaction`

```json
{
  "amount": "<number>",
  "balanceAfter": "<number>",
  "bookingId": "<string>",
  "currency": "<string>",
  "description": "<string>",
  "failureReason": "<string>",
  "gateway": "<string>",
  "id": "<string>",
  "lotId": "<string>",
  "lotName": "<string>",
  "method": "<string>",
  "referenceId": "<string>",
  "spotId": "<string>",
  "status": "<string>",
  "timestamp": "<string>",
  "type": "<string>"
}
```

### WalletTransactionsResponse

APK class: `com.gridee.parking.data.model.WalletTransactionsResponse`

```json
{
  "content": "<List<WalletTransaction>>",
  "last": "<boolean>",
  "number": "<integer>",
  "totalElements": "<integer>",
  "totalPages": "<integer>"
}
```
