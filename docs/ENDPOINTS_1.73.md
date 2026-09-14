# Gridee APK endpoint audit

- APK: `C:\Users\yashasvi\Downloads\gridee_cli\analysis\gridee-1.73-base.apk`
- Application ID: `com.gridee.parking`
- Version: `1.73` (code `74`)
- Unique Retrofit endpoints: **54**
- Retrofit declarations: **60**
- Request/response models extracted: **38**


Patterns below are inferred from Retrofit annotations and APK model fields.
They describe JSON structure, not server-side authorization or value constraints.

| Method | Route | Request pattern | Response pattern | Query |
|---|---|---|---|---|
| PUT | `/api/admin/bookings/{userId}/{bookingId}` | `Map` | `Booking` | - |
| POST | `/api/auth/firebase/exchange` | `FirebaseTokenExchangeRequest` | `AuthResponse` | - |
| POST | `/api/auth/google` | `Map` | `AuthResponse` | - |
| POST | `/api/auth/login` | `AuthRequest` | `AuthResponse` | - |
| POST | `/api/auth/register` | `UserRegistration` | `AuthResponse` | - |
| GET | `/api/bookings/{userId}/all` | `none` | `JsonElement` | - |
| GET | `/api/bookings/{userId}/all/history` | `none` | `JsonElement` | - |
| POST | `/api/bookings/{userId}/checkin/{bookingId}` | `CheckInRequest` | `Booking` | - |
| POST | `/api/bookings/{userId}/checkout/{bookingId}` | `CheckInRequest` | `Booking` | - |
| POST | `/api/bookings/{userId}/create` | `CreateBookingRequest` | `Booking` | - |
| GET | `/api/bookings/{userId}/{bookingId}` | `none` | `Booking` | - |
| POST | `/api/bookings/{userId}/{bookingId}/cancel` | `none` | `null` | - |
| PUT | `/api/bookings/{userId}/{bookingId}/extend` | `Map` | `Booking` | - |
| GET | `/api/bookings/{userId}/{bookingId}/penalty` | `none` | `number` | - |
| GET | `/api/bookings/{userId}/{bookingId}/priceBreakup` | `none` | `Map<string, object>` | - |
| GET | `/api/config/all` | `none` | `AppConfigResponse` | - |
| GET | `/api/custom-ads/active` | `none` | `JsonElement` | placement, platform, parkingLotId |
| POST | `/api/custom-ads/{adId}/click` | `none` | `null` | - |
| POST | `/api/custom-ads/{adId}/impression` | `none` | `null` | - |
| DELETE | `/api/notifications/tokens` | `DeviceTokenUnregisterRequest` | `null` | - |
| POST | `/api/notifications/tokens` | `DeviceTokenRegisterRequest` | `null` | - |
| GET | `/api/oauth2/user` | `none` | `Map<string, object>` | - |
| POST | `/api/operator/bookings/checkin` | `CheckInRequest` | `Booking` | - |
| POST | `/api/operator/bookings/checkout` | `CheckInRequest` | `Booking` | - |
| GET | `/api/operator/parking-lots/{lotId}/spots` | `none` | `JsonElement` | - |
| POST | `/api/operator/parking-lots/{parkingLotId}/bookings/checkin` | `CheckInRequest` | `Booking` | - |
| POST | `/api/operator/parking-lots/{parkingLotId}/bookings/checkout` | `CheckInRequest` | `Booking` | - |
| GET | `/api/operator/parking-spots` | `none` | `List<ParkingSpot> / JsonElement` | - |
| GET | `/api/parking-lots` | `none` | `List<ParkingLot> / JsonElement` | organizationType |
| GET | `/api/parking-lots/list/by-names` | `none` | `List<string>` | - |
| GET | `/api/parking-lots/search/by-name` | `none` | `ParkingLot` | name |
| GET | `/api/parking-lots/{lotId}/booking-policy` | `none` | `ParkingLotBookingPolicy` | - |
| GET | `/api/parking-lots/{lotId}/bookings/{userId}/all` | `none` | `JsonElement` | - |
| POST | `/api/parking-lots/{lotId}/bookings/{userId}/create` | `CreateBookingRequest` | `Booking` | - |
| GET | `/api/parking-lots/{lotId}/bookings/{userId}/history` | `none` | `JsonElement` | - |
| GET | `/api/parking-lots/{lotId}/bookings/{userId}/{bookingId}` | `none` | `Booking` | - |
| GET | `/api/parking-lots/{lotId}/spots` | `none` | `List<ParkingSpot> / JsonElement` | - |
| GET | `/api/parking-lots/{lotId}/spots/available` | `none` | `List<SpotAvailabilityInfo>` | startTime, endTime |
| GET | `/api/parking-lots/{lotId}/spots/{spotId}/available` | `none` | `boolean` | startTime, endTime |
| GET | `/api/parking-spots` | `none` | `List<ParkingSpot> / JsonElement` | - |
| GET | `/api/parking-spots/available` | `none` | `List<SpotAvailabilityInfo>` | lotId, startTime, endTime |
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
{
  "data": "<AppRemoteConfig>",
  "error": "<string>",
  "message": "<string>",
  "status": "<integer>",
  "success": "<boolean>",
  "timestamp": "<integer>"
}
```

### AppRemoteConfig

APK class: `com.gridee.parking.data.model.AppRemoteConfig`

```json
{
  "booking": "<RemoteBookingSettings>",
  "cacheTtlSeconds": "<integer>",
  "createdAt": "<integer>",
  "customSettings": "<Map<string, object>>",
  "description": "<string>",
  "features": "<RemoteFeatureFlags>",
  "financial": "<RemoteFinancialSettings>",
  "home": "<RemoteHomeSettings>",
  "id": "<string>",
  "lastUpdatedAt": "<integer>",
  "notification": "<RemoteNotificationSettings>",
  "platform": "<RemotePlatformSettings>",
  "schemaVersion": "<integer>",
  "updatedBy": "<string>",
  "versions": "<RemoteAppVersions>"
}
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
  "welcomeBonusAmount": "<number>"
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

### RemoteAppVersions

APK class: `com.gridee.parking.data.model.RemoteAppVersions`

```json
{
  "androidPlayStoreUrl": "<string>",
  "androidUpdateMessage": "<string>",
  "forceAndroidUpdate": "<boolean>",
  "forceIOSUpdate": "<boolean>",
  "iosAppStoreUrl": "<string>",
  "iosUpdateMessage": "<string>",
  "latestAndroidVersion": "<string>",
  "latestAndroidVersionCode": "<integer>",
  "latestIOSVersion": "<string>",
  "minAndroidVersion": "<string>",
  "minAndroidVersionCode": "<integer>",
  "minIOSVersion": "<string>",
  "recommendedAndroidUpdate": "<boolean>",
  "recommendedIOSUpdate": "<boolean>",
  "webVersion": "<string>"
}
```

### RemoteBookingSettings

APK class: `com.gridee.parking.data.model.RemoteBookingSettings`

```json
{
  "allowSequentialBookings": "<boolean>",
  "autoActivateNextBooking": "<boolean>",
  "autoFinalizeOverdueCheckoutMinutes": "<integer>",
  "autoFinalizeOverdueCheckouts": "<boolean>",
  "bookingValidationRules": "<Map<string, object>>",
  "maxBookingDurationHours": "<integer>",
  "maxConcurrentBookingsPerUser": "<integer>",
  "maxPricingPerHour": "<number>",
  "maxSequentialBookings": "<integer>",
  "minBookingDurationMinutes": "<integer>",
  "noShowGraceMinutes": "<integer>"
}
```

### RemoteFeatureFlags

APK class: `com.gridee.parking.data.model.RemoteFeatureFlags`

```json
{
  "adMobEnabled": "<boolean>",
  "bookingFeatureEnabled": "<boolean>",
  "bookingTransitionInterstitialEnabled": "<boolean>",
  "bookingTransitionPreloadBufferEnabled": "<boolean>",
  "emailNotificationsEnabled": "<boolean>",
  "emailSignInEnabled": "<boolean>",
  "featureToggleMap": "<Map<string, boolean>>",
  "googleSignInEnabled": "<boolean>",
  "locationTrackingEnabled": "<boolean>",
  "maintenanceMessage": "<string>",
  "maintenanceMode": "<boolean>",
  "maintenanceTitle": "<string>",
  "multipleBookingsAllowed": "<boolean>",
  "notificationsEnabled": "<boolean>",
  "pushNotificationsEnabled": "<boolean>",
  "rateLimitingEnabled": "<boolean>",
  "rewardedDailyCapEnabled": "<boolean>",
  "rewardsEnabled": "<boolean>",
  "sequentialBookingEnabled": "<boolean>",
  "walletFeatureEnabled": "<boolean>"
}
```

### RemoteFinancialSettings

APK class: `com.gridee.parking.data.model.RemoteFinancialSettings`

```json
{
  "cancellationRefundFullRefundHours": "<number>",
  "cancellationRefundPartialPercentage": "<number>",
  "cancellationRefundPartialRefundHours": "<number>",
  "customCharges": "<Map<string, number>>",
  "lateCheckoutGracePeriodMinutes": "<number>",
  "lateCheckoutPenaltyPerMin": "<number>",
  "maxLateCheckoutPenaltyPerMin": "<number>",
  "maxWalletTopUpAmount": "<number>",
  "minWalletTopUpAmount": "<number>",
  "noShowDeduction": "<number>",
  "overdueCheckoutPenaltyPercentage": "<number>",
  "paymentGatewayTaxPercentage": "<number>",
  "penaltyEscalationIntervalMins": "<integer>",
  "welcomeBonusAmount": "<number>"
}
```

### RemoteHomeSettings

APK class: `com.gridee.parking.data.model.RemoteHomeSettings`

```json
{
  "showSlotFilters": "<boolean>"
}
```

### RemoteNotificationSettings

APK class: `com.gridee.parking.data.model.RemoteNotificationSettings`

```json
{
  "checkInReminderMinutesBefore": "<integer>",
  "checkOutReminderMinutesAfter": "<integer>",
  "maxNotificationsPerUser": "<integer>",
  "notificationProvider": "<string>",
  "sendBookingConfirmation": "<boolean>",
  "sendCancellationNotification": "<boolean>",
  "sendCheckInReminders": "<boolean>",
  "sendCheckOutReminders": "<boolean>",
  "sendPenaltyNotifications": "<boolean>"
}
```

### RemotePlatformSettings

APK class: `com.gridee.parking.data.model.RemotePlatformSettings`

```json
{
  "apiVersion": "<string>",
  "currency": "<string>",
  "currencySymbol": "<string>",
  "debugMode": "<boolean>",
  "enableCors": "<boolean>",
  "enableSwagger": "<boolean>",
  "environment": "<string>",
  "externalServiceUrls": "<Map<string, string>>",
  "rateLimitPerHour": "<integer>",
  "rateLimitPerMinute": "<integer>",
  "requestTimeoutSeconds": "<integer>",
  "timezone": "<string>"
}
```

### SpotAvailabilityInfo

APK class: `com.gridee.parking.data.model.SpotAvailabilityInfo`

```json
{
  "availableCapacity": "<integer>",
  "bookedCount": "<integer>",
  "isAvailable": "<boolean>",
  "spot": "<ParkingSpot>"
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

### UserRegistration

APK class: `com.gridee.parking.data.model.UserRegistration`

```json
{
  "email": "<string>",
  "name": "<string>",
  "parkingLotName": "<string>",
  "password": "<string>",
  "phone": "<string>",
  "vehicleNumbers": "<List<string>>"
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
